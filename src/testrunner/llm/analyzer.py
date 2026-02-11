"""LLM-based test failure analysis.

This module provides failure analysis capabilities using an LLM to identify
root causes and suggest fixes for failing tests.
"""

from dataclasses import dataclass
from typing import Optional

from testrunner.llm.base import LLMClient
from testrunner.storage.models import TestResult


@dataclass
class FailureAnalysis:
    """Analysis of a test failure."""

    test_name: str
    likely_cause: str
    suspected_file: Optional[str] = None
    suspected_commit: Optional[str] = None
    confidence: float = 0.0
    explanation: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "test_name": self.test_name,
            "likely_cause": self.likely_cause,
            "suspected_file": self.suspected_file,
            "suspected_commit": self.suspected_commit,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "suggested_fix": self.suggested_fix,
        }


class FailureAnalyzer:
    """Analyzes test failures to identify root causes."""

    ANALYZER_SYSTEM_PROMPT = """You are a software testing expert who analyzes test failures to identify root causes.

Your job is to:
1. Analyze test failure error messages
2. Consider recent code changes from git
3. Identify the most likely cause of the failure
4. Suggest specific fixes

Be specific and actionable in your analysis. Focus on:
- What likely broke
- Which file or commit is suspicious
- Concrete steps to fix the issue

Return ONLY valid JSON matching the schema provided."""

    def __init__(self, llm_client: LLMClient):
        """Initialize analyzer with LLM client.

        Args:
            llm_client: LLM client for analysis
        """
        self.client = llm_client

    def analyze(
        self,
        test_result: TestResult,
        git_changes: Optional[dict] = None,
    ) -> Optional[FailureAnalysis]:
        """Analyze a test failure to identify root cause.

        Args:
            test_result: The failed test result
            git_changes: Optional git changes context from GitDiffAnalyzer

        Returns:
            FailureAnalysis if successful, None if LLM unavailable or error
        """
        if not self.client.is_available():
            return None

        if not test_result.error_message:
            # No error message to analyze
            return None

        prompt = self._build_analysis_prompt(test_result, git_changes)

        try:
            response = self.client.generate_json(
                prompt=prompt,
                system_prompt=self.ANALYZER_SYSTEM_PROMPT,
                temperature=0.3,  # Lower temperature for more focused analysis
            )

            if response:
                return self._convert_response_to_analysis(test_result.test_name, response)
            else:
                return None

        except Exception:
            return None

    def analyze_multiple(
        self,
        test_results: list[TestResult],
        git_changes: Optional[dict] = None,
    ) -> list[FailureAnalysis]:
        """Analyze multiple test failures.

        Args:
            test_results: List of failed test results
            git_changes: Optional git changes context

        Returns:
            List of FailureAnalysis objects (may be empty if errors occur)
        """
        analyses = []

        for test_result in test_results:
            analysis = self.analyze(test_result, git_changes)
            if analysis:
                analyses.append(analysis)

        return analyses

    def _build_analysis_prompt(
        self,
        test_result: TestResult,
        git_changes: Optional[dict],
    ) -> str:
        """Build analysis prompt for LLM.

        Args:
            test_result: Failed test result
            git_changes: Git changes context

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "Analyze the following test failure and identify the root cause.",
            "",
            "## Failing Test",
            f"Test: {test_result.test_name}",
            f"File: {test_result.test_file or 'unknown'}",
            "",
            "## Error Message",
            "```",
            test_result.error_message[:5000],  # Limit error message length
            "```",
            "",
        ]

        # Add git context if available
        if git_changes:
            changed_files = git_changes.get("files", [])
            recent_commits = git_changes.get("commits", [])

            if changed_files:
                prompt_parts.extend([
                    "## Recently Changed Files",
                    "",
                ])
                for file_info in changed_files[:15]:  # Limit to 15 files
                    path = file_info.get("path", "unknown")
                    change_type = file_info.get("change_type", "?")
                    prompt_parts.append(f"- {path} ({change_type})")
                prompt_parts.append("")

            if recent_commits:
                prompt_parts.extend([
                    "## Recent Commits",
                    "",
                ])
                for commit in recent_commits[:10]:  # Limit to 10 commits
                    short_hash = commit.get("short_hash", "?")
                    message = commit.get("message", "")[:80]
                    prompt_parts.append(f"- [{short_hash}] {message}")
                prompt_parts.append("")

        prompt_parts.extend([
            "## Task",
            "",
            "Identify the most likely cause of this test failure. Consider:",
            "1. The error message and stack trace",
            "2. Recently changed files that might be related",
            "3. Recent commits that might have introduced the issue",
            "",
            "Provide a specific, actionable analysis.",
            "",
            "Respond with valid JSON matching this exact schema:",
            "```json",
            "{",
            '  "likely_cause": "Brief description of what likely caused the failure",',
            '  "suspected_file": "path/to/file.py or null if unknown",',
            '  "suspected_commit": "commit_hash or null if unknown",',
            '  "confidence": 0.75,',
            '  "explanation": "Detailed explanation of why you think this is the cause",',
            '  "suggested_fix": "Specific steps or code changes to fix the issue"',
            "}",
            "```",
            "",
            "Important: Return ONLY the JSON, no additional text.",
        ])

        return "\n".join(prompt_parts)

    def _convert_response_to_analysis(
        self,
        test_name: str,
        response: dict,
    ) -> FailureAnalysis:
        """Convert LLM JSON response to FailureAnalysis.

        Args:
            test_name: Name of the failed test
            response: Parsed JSON from LLM

        Returns:
            FailureAnalysis object
        """
        return FailureAnalysis(
            test_name=test_name,
            likely_cause=response.get("likely_cause", "Unknown"),
            suspected_file=response.get("suspected_file"),
            suspected_commit=response.get("suspected_commit"),
            confidence=float(response.get("confidence", 0.5)),
            explanation=response.get("explanation", ""),
            suggested_fix=response.get("suggested_fix", ""),
        )
