"""Test execution orchestration."""

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from testrunner.config import TestRunnerConfig
from testrunner.core.discovery import TestDiscovery
from testrunner.core.parser import ResultParser
from testrunner.storage.database import Database
from testrunner.storage.models import TestResult, TestRun, TestStatus


class TestRunner:
    """Orchestrates test execution with intelligent prioritization."""

    def __init__(
        self,
        config: TestRunnerConfig,
        database: Database,
        base_dir: Path,
        verbose: bool = False,
    ):
        """Initialize the test runner."""
        self.config = config
        self.db = database
        self.base_dir = base_dir
        self.verbose = verbose

        self.discovery = TestDiscovery(config, base_dir)
        self.parser = ResultParser(config.test.command)

        # Analysis data collected during run
        self._git_changes: dict[str, Any] = {}
        self._risk_scores: dict[str, float] = {}
        self._root_cause_analysis: list[dict] = []
        self._current_run: Optional[TestRun] = None

    def analyze_git_changes(self) -> dict[str, Any]:
        """Analyze git changes in the repository."""
        if not self.config.git.enabled:
            return {}

        try:
            from testrunner.git.diff import GitDiffAnalyzer

            analyzer = GitDiffAnalyzer(self.base_dir)
            self._git_changes = analyzer.analyze(
                compare_ref=self.config.git.compare_ref,
                include_uncommitted=self.config.git.include_uncommitted,
            )
            return self._git_changes
        except Exception as e:
            if self.verbose:
                print(f"Git analysis error: {e}")
            return {}

    def analyze_risks(self) -> dict[str, float]:
        """Analyze test risks using LLM and historical data."""
        try:
            from testrunner.risk.scorer import RiskScorer

            scorer = RiskScorer(self.config, self.db, self.base_dir)
            self._risk_scores = scorer.compute_scores(
                git_changes=self._git_changes,
                hints=self.config.get_hints_content(self.base_dir),
            )
            return self._risk_scores
        except Exception as e:
            if self.verbose:
                print(f"Risk analysis error: {e}")
            return {}

    def execute_tests(self, priority_only: bool = False) -> dict[str, Any]:
        """Execute tests and return results."""
        # Get git info for the run
        commit_hash = None
        branch = None

        if self.config.git.enabled:
            try:
                from testrunner.git.diff import GitDiffAnalyzer

                analyzer = GitDiffAnalyzer(self.base_dir)
                commit_hash = analyzer.get_current_commit()
                branch = analyzer.get_current_branch()
            except Exception:
                pass

        # Create test run record
        self._current_run = self.db.create_run(
            commit_hash=commit_hash,
            branch=branch,
        )

        # Build test command
        cmd = self._build_command(priority_only)

        # Execute tests
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.base_dir,
                timeout=self.config.test.timeout_seconds,
            )

            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode

        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = "Test execution timed out"
            return_code = -1
        except Exception as e:
            stdout = ""
            stderr = str(e)
            return_code = -1

        # Parse results
        json_output = self._get_json_output()
        parsed = self.parser.parse(stdout, stderr, return_code, json_output)

        # Store results
        results_dict = self._store_results(parsed)

        # Perform root cause analysis for failures
        if parsed.failed > 0:
            self._analyze_root_cause(parsed)

        return results_dict

    def _build_command(self, priority_only: bool = False) -> list[str]:
        """Build the test command."""
        cmd = [self.config.test.command]
        cmd.extend(self.config.test.args)

        # Add pytest-specific options for better output
        if "pytest" in self.config.test.command.lower():
            # Add JSON output if pytest-json-report is available
            self._json_report_path = None
            try:
                import pytest_json_report

                self._json_report_path = tempfile.mktemp(suffix=".json")
                cmd.extend(["--json-report", f"--json-report-file={self._json_report_path}"])
            except ImportError:
                pass

            # Add verbose output
            if "-v" not in cmd and "--verbose" not in cmd:
                cmd.append("-v")

            # Add fail-fast if configured
            if self.config.test.fail_fast and "-x" not in cmd:
                cmd.append("-x")

            # If priority_only, run high-risk tests first
            if priority_only and self._risk_scores:
                # Sort by risk score and take top tests
                high_risk_tests = sorted(
                    self._risk_scores.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:10]  # Top 10 high-risk tests

                if high_risk_tests:
                    test_names = [t[0] for t in high_risk_tests]
                    cmd.extend(test_names)
                    return cmd

        # Add test directory
        cmd.append(str(self.base_dir / self.config.test.test_directory))

        return cmd

    def _get_json_output(self) -> Optional[dict]:
        """Get JSON output if available."""
        if hasattr(self, "_json_report_path") and self._json_report_path:
            try:
                with open(self._json_report_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _store_results(self, parsed) -> dict[str, Any]:
        """Store parsed results in the database."""
        if not self._current_run:
            return {}

        # Update run statistics
        self._current_run.total_tests = parsed.total
        self._current_run.passed = parsed.passed
        self._current_run.failed = parsed.failed
        self._current_run.skipped = parsed.skipped

        # Store individual results
        for result in parsed.results:
            result.run_id = self._current_run.id

            # Add risk score if available
            if result.test_name in self._risk_scores:
                result.risk_score = self._risk_scores[result.test_name]

            self.db.add_result(result)

        # Finish the run
        self.db.finish_run(self._current_run)

        # Build results dictionary
        return {
            "run_id": self._current_run.id,
            "total": parsed.total,
            "passed": parsed.passed,
            "failed": parsed.failed,
            "skipped": parsed.skipped,
            "duration_ms": parsed.duration_ms,
            "results": [r.to_dict() for r in parsed.results],
            "failed_tests": [
                r.to_dict() for r in parsed.results if r.status == TestStatus.FAILED
            ],
            "raw_output": parsed.raw_output,
        }

    def _analyze_root_cause(self, parsed) -> None:
        """Perform root cause analysis for failed tests."""
        if not parsed.failed:
            return

        try:
            from testrunner.llm.analysis import TestAnalyzer

            analyzer = TestAnalyzer(self.config, self.base_dir)

            failed_tests = [r for r in parsed.results if r.status == TestStatus.FAILED]

            for test in failed_tests:
                analysis = analyzer.analyze_failure(
                    test_name=test.test_name,
                    error_message=test.error_message,
                    git_changes=self._git_changes,
                )
                if analysis:
                    self._root_cause_analysis.append(analysis.to_dict())

        except Exception as e:
            if self.verbose:
                print(f"Root cause analysis error: {e}")

    def get_analysis_data(self) -> dict[str, Any]:
        """Get all analysis data collected during the run."""
        return {
            "git_changes": self._git_changes,
            "risk_scores": self._risk_scores,
            "root_cause_analysis": self._root_cause_analysis,
        }
