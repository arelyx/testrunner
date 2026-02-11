"""LLM-based universal test output parser.

This module provides a language-agnostic test output parser that uses an LLM
to understand and parse test results from any testing framework.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

from testrunner.llm.base import LLMClient
from testrunner.storage.models import TestResult, TestStatus


@dataclass
class ParsedTestOutput:
    """Structured test output parsed from raw command output."""

    tests: list[TestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: int = 0
    raw_output: str = ""
    parse_confidence: float = 1.0  # LLM's confidence in parsing accuracy

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "tests": [t.to_dict() for t in self.tests],
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_ms": self.duration_ms,
            "raw_output": self.raw_output,
            "parse_confidence": self.parse_confidence,
        }


class LLMOutputParser:
    """Universal test output parser using LLM interpretation."""

    PARSER_SYSTEM_PROMPT = """You are a test output parser. Your job is to analyze test framework output from ANY language or framework and extract structured test results.

You understand many testing frameworks:
- Python: pytest, unittest, nose
- JavaScript/TypeScript: Jest, Mocha, Jasmine, Vitest
- Go: go test
- Java: JUnit, TestNG
- Rust: cargo test
- Ruby: RSpec, Minitest
- And many others

Be accurate and thorough in extracting:
1. Individual test names/identifiers
2. Test status (passed/failed/skipped/error)
3. Test file paths
4. Duration if available
5. Error messages for failures

Return ONLY valid JSON matching the exact schema provided."""

    def __init__(self, llm_client: LLMClient):
        """Initialize parser with LLM client.

        Args:
            llm_client: LLM client for parsing
        """
        self.client = llm_client

    def parse(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        test_command: Optional[str] = None,
        language: Optional[str] = None,
        hints: Optional[str] = None,
    ) -> ParsedTestOutput:
        """Parse raw test output into structured results.

        Args:
            stdout: Standard output from test command
            stderr: Standard error from test command
            exit_code: Exit code from test command
            test_command: The command that was run (helps LLM understand framework)
            language: Optional language hint (e.g., "python", "javascript")
            hints: Optional project context from HINTS.md

        Returns:
            ParsedTestOutput with structured test results
        """
        if not self.client.is_available():
            return self._fallback_parse(stdout, stderr, exit_code)

        # Build parsing prompt
        prompt = self._build_parse_prompt(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            test_command=test_command,
            language=language,
            hints=hints,
        )

        # Get LLM response
        try:
            response = self.client.generate_json(
                prompt=prompt,
                system_prompt=self.PARSER_SYSTEM_PROMPT,
                temperature=0.1,  # Low temperature for deterministic parsing
            )

            if response:
                return self._convert_response_to_output(response, stdout)
            else:
                return self._fallback_parse(stdout, stderr, exit_code)

        except Exception as e:
            # If LLM fails, use simple fallback
            return self._fallback_parse(stdout, stderr, exit_code)

    def _build_parse_prompt(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        test_command: Optional[str],
        language: Optional[str],
        hints: Optional[str] = None,
    ) -> str:
        """Build the parsing prompt for the LLM.

        Args:
            stdout: Standard output
            stderr: Standard error
            exit_code: Exit code
            test_command: Test command executed
            language: Language hint
            hints: Optional project context from HINTS.md

        Returns:
            Formatted prompt string
        """
        # Truncate output if too long (to avoid token limits)
        max_output_length = 15000
        stdout_truncated = stdout[:max_output_length]
        stderr_truncated = stderr[:max_output_length]

        if len(stdout) > max_output_length:
            stdout_truncated += "\n... (output truncated)"
        if len(stderr) > max_output_length:
            stderr_truncated += "\n... (output truncated)"

        prompt_parts = [
            "Parse the following test output and extract structured results.",
            "",
            "Context:",
        ]

        if test_command:
            prompt_parts.append(f"- Test command: `{test_command}`")
        if language:
            prompt_parts.append(f"- Language/Framework: {language}")

        if hints:
            prompt_parts.extend([
                "",
                "## Project Hints",
                hints[:5000],  # Limit hints length
                "",
            ])

        prompt_parts.extend([
            f"- Exit code: {exit_code}",
            "",
            "STDOUT:",
            "```",
            stdout_truncated,
            "```",
            "",
        ])

        if stderr_truncated.strip():
            prompt_parts.extend([
                "STDERR:",
                "```",
                stderr_truncated,
                "```",
                "",
            ])

        prompt_parts.extend([
            "Extract ALL individual test results. For each test, provide:",
            "- name: The full test identifier/name",
            "- file: The test file path (if identifiable)",
            "- status: One of 'passed', 'failed', 'skipped', or 'error'",
            "- duration_ms: Test duration in milliseconds (0 if not available)",
            "- error_message: Full error message if failed (null otherwise)",
            "",
            "Also provide summary statistics:",
            "- total: Total number of tests",
            "- passed: Number of passed tests",
            "- failed: Number of failed tests",
            "- skipped: Number of skipped tests",
            "- duration_ms: Total test run duration",
            "",
            "Respond with valid JSON matching this exact schema:",
            "```json",
            "{",
            '  "tests": [',
            "    {",
            '      "name": "test_name_or_identifier",',
            '      "file": "path/to/test/file",',
            '      "status": "passed|failed|skipped|error",',
            '      "duration_ms": 0,',
            '      "error_message": "error details or null"',
            "    }",
            "  ],",
            '  "summary": {',
            '    "total": 10,',
            '    "passed": 8,',
            '    "failed": 1,',
            '    "skipped": 1,',
            '    "duration_ms": 1234',
            "  }",
            "}",
            "```",
            "",
            "Important: Return ONLY the JSON, no additional text or explanations.",
        ])

        return "\n".join(prompt_parts)

    def _convert_response_to_output(
        self,
        response: dict,
        raw_output: str,
    ) -> ParsedTestOutput:
        """Convert LLM JSON response to ParsedTestOutput.

        Args:
            response: Parsed JSON from LLM
            raw_output: Original raw output

        Returns:
            ParsedTestOutput object
        """
        tests = []

        for test_data in response.get("tests", []):
            # Parse status
            status_str = test_data.get("status", "error").lower()
            status_map = {
                "passed": TestStatus.PASSED,
                "failed": TestStatus.FAILED,
                "skipped": TestStatus.SKIPPED,
                "error": TestStatus.ERROR,
            }
            status = status_map.get(status_str, TestStatus.ERROR)

            test = TestResult(
                test_name=test_data.get("name", "unknown"),
                test_file=test_data.get("file", ""),
                status=status,
                duration_ms=int(test_data.get("duration_ms", 0)),
                error_message=test_data.get("error_message") or "",
            )
            tests.append(test)

        # Get summary
        summary = response.get("summary", {})

        return ParsedTestOutput(
            tests=tests,
            total=summary.get("total", len(tests)),
            passed=summary.get("passed", 0),
            failed=summary.get("failed", 0),
            skipped=summary.get("skipped", 0),
            duration_ms=summary.get("duration_ms", 0),
            raw_output=raw_output,
            parse_confidence=1.0,  # Assume high confidence from LLM
        )

    def _fallback_parse(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> ParsedTestOutput:
        """Simple fallback parser when LLM is unavailable.

        This provides basic parsing by looking for common patterns.
        Not as accurate as LLM parsing but better than nothing.

        Args:
            stdout: Standard output
            stderr: Standard error
            exit_code: Exit code

        Returns:
            ParsedTestOutput with basic parsing
        """
        import re

        combined = stdout + "\n" + stderr

        # Try to count passes/failures with common patterns
        passed = len(re.findall(r'\b(PASS|PASSED|OK|✓)\b', combined, re.IGNORECASE))
        failed = len(re.findall(r'\b(FAIL|FAILED|ERROR|FAILED|✗)\b', combined, re.IGNORECASE))
        skipped = len(re.findall(r'\b(SKIP|SKIPPED|○)\b', combined, re.IGNORECASE))

        # If exit code is non-zero but we found no failures, mark at least one failure
        if exit_code != 0 and failed == 0:
            failed = 1

        total = passed + failed + skipped

        return ParsedTestOutput(
            tests=[],  # Can't extract individual tests without LLM
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_ms=0,
            raw_output=combined,
            parse_confidence=0.3,  # Low confidence for fallback
        )
