"""Test result parsing functionality."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from testrunner.storage.models import TestResult, TestStatus


@dataclass
class ParsedResult:
    """Parsed result from test output."""

    results: list[TestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: int = 0
    raw_output: str = ""


class ResultParser:
    """Parses test output from various frameworks."""

    def __init__(self, command: str):
        """Initialize parser for the given test command."""
        self.command = command.lower()

    def parse(
        self,
        stdout: str,
        stderr: str,
        return_code: int,
        json_output: Optional[dict] = None,
    ) -> ParsedResult:
        """Parse test output based on the test framework."""
        if "pytest" in self.command:
            if json_output:
                return self._parse_pytest_json(json_output, stdout)
            return self._parse_pytest_stdout(stdout, stderr, return_code)
        else:
            return self._parse_generic(stdout, stderr, return_code)

    def _parse_pytest_json(self, data: dict, raw_output: str) -> ParsedResult:
        """Parse pytest JSON report output."""
        results = []

        tests = data.get("tests", [])
        summary = data.get("summary", {})

        for test in tests:
            nodeid = test.get("nodeid", "")
            outcome = test.get("outcome", "unknown")

            # Map pytest outcomes to our status
            status_map = {
                "passed": TestStatus.PASSED,
                "failed": TestStatus.FAILED,
                "skipped": TestStatus.SKIPPED,
                "error": TestStatus.ERROR,
                "xfailed": TestStatus.SKIPPED,
                "xpassed": TestStatus.PASSED,
            }
            status = status_map.get(outcome, TestStatus.ERROR)

            # Extract file and test name
            parts = nodeid.split("::")
            file_path = parts[0] if parts else ""
            test_name = nodeid

            # Get duration in milliseconds
            duration = test.get("duration", 0)
            duration_ms = int(duration * 1000)

            # Get error message if failed
            error_message = ""
            call_info = test.get("call", {})
            if call_info.get("longrepr"):
                error_message = str(call_info["longrepr"])

            result = TestResult(
                test_name=test_name,
                test_file=file_path,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
            )
            results.append(result)

        return ParsedResult(
            results=results,
            total=summary.get("total", len(tests)),
            passed=summary.get("passed", 0),
            failed=summary.get("failed", 0),
            skipped=summary.get("skipped", 0),
            errors=summary.get("error", 0),
            duration_ms=int(data.get("duration", 0) * 1000),
            raw_output=raw_output,
        )

    def _parse_pytest_stdout(
        self, stdout: str, stderr: str, return_code: int
    ) -> ParsedResult:
        """Parse pytest stdout output."""
        results = []
        combined = stdout + "\n" + stderr

        # Parse individual test results
        # Format: tests/test_file.py::test_name PASSED/FAILED/SKIPPED
        test_pattern = r"^([\w/\\._-]+\.py(?:::\w+)*)\s+(PASSED|FAILED|SKIPPED|ERROR)"
        
        for match in re.finditer(test_pattern, combined, re.MULTILINE):
            test_name = match.group(1)
            status_str = match.group(2)

            status_map = {
                "PASSED": TestStatus.PASSED,
                "FAILED": TestStatus.FAILED,
                "SKIPPED": TestStatus.SKIPPED,
                "ERROR": TestStatus.ERROR,
            }
            status = status_map.get(status_str, TestStatus.ERROR)

            # Extract file path
            parts = test_name.split("::")
            file_path = parts[0] if parts else ""

            result = TestResult(
                test_name=test_name,
                test_file=file_path,
                status=status,
            )
            results.append(result)

        # Parse summary line
        # Format: ===== 5 passed, 2 failed, 1 skipped in 0.23s =====
        summary_pattern = r"=+\s*([\d\w\s,]+)\s+in\s+([\d.]+)s?\s*=+"
        summary_match = re.search(summary_pattern, combined)

        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        duration_ms = 0

        if summary_match:
            summary_text = summary_match.group(1)
            duration_str = summary_match.group(2)
            duration_ms = int(float(duration_str) * 1000)

            # Parse counts
            count_pattern = r"(\d+)\s+(\w+)"
            for count_match in re.finditer(count_pattern, summary_text):
                count = int(count_match.group(1))
                status_type = count_match.group(2).lower()

                if "pass" in status_type:
                    passed = count
                elif "fail" in status_type:
                    failed = count
                elif "skip" in status_type:
                    skipped = count
                elif "error" in status_type:
                    errors = count

        # Extract error messages for failed tests
        error_sections = self._extract_pytest_errors(combined)
        for result in results:
            if result.status == TestStatus.FAILED and result.test_name in error_sections:
                result.error_message = error_sections[result.test_name]

        total = passed + failed + skipped + errors
        if not results and total > 0:
            # If we didn't parse individual results, create placeholder results
            pass

        return ParsedResult(
            results=results,
            total=total or len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            duration_ms=duration_ms,
            raw_output=combined,
        )

    def _extract_pytest_errors(self, output: str) -> dict[str, str]:
        """Extract error messages from pytest output."""
        errors = {}

        # Pattern to match failure sections
        # Format: _____ test_name _____
        failure_pattern = r"_{3,}\s*([\w:./\\-]+)\s*_{3,}"
        sections = re.split(failure_pattern, output)

        # Pair up section names with their content
        for i in range(1, len(sections), 2):
            if i + 1 < len(sections):
                test_name = sections[i].strip()
                error_content = sections[i + 1].strip()

                # Limit error message length
                if len(error_content) > 2000:
                    error_content = error_content[:2000] + "\n... (truncated)"

                errors[test_name] = error_content

        return errors

    def _parse_generic(
        self, stdout: str, stderr: str, return_code: int
    ) -> ParsedResult:
        """Generic parser for unknown test frameworks."""
        combined = stdout + "\n" + stderr

        # Try to detect pass/fail patterns
        passed = len(re.findall(r"\b(PASS|OK|SUCCESS)\b", combined, re.IGNORECASE))
        failed = len(re.findall(r"\b(FAIL|ERROR|FAILED)\b", combined, re.IGNORECASE))

        return ParsedResult(
            results=[],
            total=passed + failed,
            passed=passed,
            failed=failed,
            skipped=0,
            errors=0,
            duration_ms=0,
            raw_output=combined,
        )
