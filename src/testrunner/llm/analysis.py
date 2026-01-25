"""LLM-based test analysis functionality."""

from pathlib import Path
from typing import Any, Optional

from testrunner.config import TestRunnerConfig
from testrunner.llm.base import LLMClient
from testrunner.llm.ollama import OllamaClient
from testrunner.llm.prompts import PromptTemplates
from testrunner.storage.models import RiskAnalysis, RootCauseAnalysis


def get_llm_client(config: TestRunnerConfig) -> LLMClient:
    """Get the appropriate LLM client based on configuration."""
    if config.llm.provider == "ollama":
        return OllamaClient(
            base_url=config.llm.base_url,
            model=config.llm.model,
            timeout=config.llm.timeout_seconds,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")


class TestAnalyzer:
    """Performs LLM-based test analysis."""

    def __init__(self, config: TestRunnerConfig, base_dir: Path):
        """Initialize the analyzer.

        Args:
            config: TestRunner configuration
            base_dir: Base directory of the project
        """
        self.config = config
        self.base_dir = base_dir
        self.client = get_llm_client(config)

    def analyze_risk(
        self,
        changed_files: list[dict],
        test_files: list[str],
        hints: Optional[str] = None,
        historical_failures: Optional[list[dict]] = None,
    ) -> list[RiskAnalysis]:
        """Analyze test risk based on code changes.

        Args:
            changed_files: List of changed file info
            test_files: List of test file paths
            hints: Optional hints content
            historical_failures: Optional historical failure data

        Returns:
            List of RiskAnalysis results
        """
        if not self.client.is_available():
            return []

        prompt = PromptTemplates.risk_analysis_prompt(
            changed_files=changed_files,
            test_files=test_files,
            hints=hints,
            historical_failures=historical_failures,
        )

        response = self.client.generate_json(
            prompt=prompt,
            system_prompt=PromptTemplates.SYSTEM_PROMPT,
            temperature=0.3,
        )

        if not response:
            return []

        results = []
        high_risk_tests = response.get("high_risk_tests", [])

        for test in high_risk_tests:
            analysis = RiskAnalysis(
                test_name=test.get("test_name", ""),
                risk_score=float(test.get("risk_score", 0.5)),
                risk_factors=[test.get("reason", "")] if test.get("reason") else [],
                affected_by_changes=True,
                llm_confidence=float(test.get("risk_score", 0.5)),
            )
            results.append(analysis)

        return results

    def analyze_failure(
        self,
        test_name: str,
        error_message: str,
        git_changes: Optional[dict[str, Any]] = None,
    ) -> Optional[RootCauseAnalysis]:
        """Analyze a test failure to identify root cause.

        Args:
            test_name: Name of the failing test
            error_message: Error message from the test
            git_changes: Optional git changes data

        Returns:
            RootCauseAnalysis or None if analysis fails
        """
        if not self.client.is_available():
            return None

        changed_files = git_changes.get("files", []) if git_changes else []
        recent_commits = git_changes.get("commits", []) if git_changes else []

        prompt = PromptTemplates.root_cause_prompt(
            test_name=test_name,
            error_message=error_message,
            changed_files=changed_files,
            recent_commits=recent_commits,
        )

        response = self.client.generate_json(
            prompt=prompt,
            system_prompt=PromptTemplates.SYSTEM_PROMPT,
            temperature=0.3,
        )

        if not response:
            return None

        return RootCauseAnalysis(
            test_name=test_name,
            likely_cause=response.get("likely_cause", "Unknown"),
            commit_hash=response.get("suspected_commit"),
            file_path=response.get("suspected_file"),
            confidence=float(response.get("confidence", 0.5)),
            explanation=response.get("explanation", ""),
            suggested_fix=response.get("suggested_fix", ""),
        )

    def analyze_test_impact(
        self,
        file_path: str,
        file_diff: str,
        test_files: list[str],
    ) -> list[dict]:
        """Analyze which tests might be affected by a file change.

        Args:
            file_path: Path of the changed file
            file_diff: Git diff of the file
            test_files: List of available test files

        Returns:
            List of affected test info dicts
        """
        if not self.client.is_available():
            return []

        prompt = PromptTemplates.test_impact_prompt(
            file_path=file_path,
            file_diff=file_diff,
            test_files=test_files,
        )

        response = self.client.generate_json(
            prompt=prompt,
            system_prompt=PromptTemplates.SYSTEM_PROMPT,
            temperature=0.3,
        )

        if not response:
            return []

        return response.get("affected_tests", [])

    def summarize_results(
        self,
        passed: int,
        failed: int,
        skipped: int,
        failed_tests: list[dict],
        risk_predictions: Optional[list[dict]] = None,
    ) -> str:
        """Generate a summary of test results.

        Args:
            passed: Number of passed tests
            failed: Number of failed tests
            skipped: Number of skipped tests
            failed_tests: List of failed test info
            risk_predictions: Optional predictions that were made

        Returns:
            Summary text
        """
        if not self.client.is_available():
            return "LLM unavailable for summary generation."

        prompt = PromptTemplates.summarize_results_prompt(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failed_tests=failed_tests,
            risk_predictions=risk_predictions,
        )

        response = self.client.generate(
            prompt=prompt,
            system_prompt=PromptTemplates.SYSTEM_PROMPT,
            temperature=0.5,
        )

        return response.content if response.success else "Unable to generate summary."
