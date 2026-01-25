"""Prompt templates for LLM interactions."""

from typing import Any, Optional


class PromptTemplates:
    """Collection of prompt templates for test analysis."""

    SYSTEM_PROMPT = """You are an expert software testing assistant. Your role is to:
1. Analyze code changes and predict which tests are likely to be affected
2. Identify potential causes of test failures
3. Provide actionable insights for debugging

Be concise and technical. Focus on practical, specific recommendations.
When providing JSON responses, ensure they are valid and parseable."""

    @staticmethod
    def risk_analysis_prompt(
        changed_files: list[dict],
        test_files: list[str],
        hints: Optional[str] = None,
        historical_failures: Optional[list[dict]] = None,
    ) -> str:
        """Generate a prompt for test risk analysis.

        Args:
            changed_files: List of changed file info dicts
            test_files: List of test file paths
            hints: Optional hints content from HINTS.md
            historical_failures: Optional list of historically failing tests

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "Analyze the following code changes and predict which tests are most likely to fail.",
            "",
            "## Changed Files",
        ]

        for f in changed_files[:20]:  # Limit to 20 files
            prompt_parts.append(f"- {f.get('path', 'unknown')} ({f.get('change_type', '?')})")
            if f.get("diff_content"):
                diff_preview = f["diff_content"][:500]
                prompt_parts.append(f"  ```\n  {diff_preview}\n  ```")

        prompt_parts.extend(["", "## Test Files"])
        for test in test_files[:30]:  # Limit to 30 tests
            prompt_parts.append(f"- {test}")

        if historical_failures:
            prompt_parts.extend(["", "## Historically Failing Tests"])
            for test in historical_failures[:10]:
                prompt_parts.append(
                    f"- {test.get('test_name', 'unknown')} "
                    f"(failure rate: {test.get('failure_rate', 0):.1%})"
                )

        if hints:
            prompt_parts.extend(["", "## Project Hints", hints[:2000]])

        prompt_parts.extend([
            "",
            "## Task",
            "Based on the code changes and test files, identify tests that are most likely to fail.",
            "For each high-risk test, explain why it might be affected by the changes.",
            "",
            "Respond with JSON in this format:",
            "```json",
            "{",
            '  "high_risk_tests": [',
            "    {",
            '      "test_name": "test_file.py::test_function",',
            '      "risk_score": 0.8,',
            '      "reason": "Brief explanation of why this test might fail"',
            "    }",
            "  ],",
            '  "summary": "Brief overall assessment"',
            "}",
            "```",
        ])

        return "\n".join(prompt_parts)

    @staticmethod
    def root_cause_prompt(
        test_name: str,
        error_message: str,
        changed_files: list[dict],
        recent_commits: Optional[list[dict]] = None,
    ) -> str:
        """Generate a prompt for root cause analysis.

        Args:
            test_name: Name of the failing test
            error_message: Error message from the test
            changed_files: List of recently changed files
            recent_commits: Optional list of recent commits

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            f"Analyze the following test failure and identify the most likely root cause.",
            "",
            "## Failing Test",
            f"Test: {test_name}",
            "",
            "## Error Message",
            "```",
            error_message[:3000] if error_message else "No error message available",
            "```",
            "",
            "## Recently Changed Files",
        ]

        for f in changed_files[:15]:
            prompt_parts.append(f"- {f.get('path', 'unknown')} ({f.get('change_type', '?')})")

        if recent_commits:
            prompt_parts.extend(["", "## Recent Commits"])
            for commit in recent_commits[:10]:
                prompt_parts.append(
                    f"- [{commit.get('short_hash', '?')}] {commit.get('message', '')[:80]}"
                )

        prompt_parts.extend([
            "",
            "## Task",
            "Identify the most likely cause of this test failure.",
            "If possible, identify which commit or file change caused the failure.",
            "",
            "Respond with JSON in this format:",
            "```json",
            "{",
            '  "likely_cause": "Brief description of the root cause",',
            '  "suspected_commit": "commit_hash or null",',
            '  "suspected_file": "path/to/file.py or null",',
            '  "confidence": 0.75,',
            '  "explanation": "Detailed explanation of the analysis",',
            '  "suggested_fix": "Recommended action to fix the issue"',
            "}",
            "```",
        ])

        return "\n".join(prompt_parts)

    @staticmethod
    def test_impact_prompt(
        file_path: str,
        file_diff: str,
        test_files: list[str],
    ) -> str:
        """Generate a prompt to analyze which tests might be affected by a file change.

        Args:
            file_path: Path of the changed file
            file_diff: Git diff of the file
            test_files: List of available test files

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            f"Analyze which tests might be affected by changes to: {file_path}",
            "",
            "## File Changes",
            "```diff",
            file_diff[:2000] if file_diff else "No diff available",
            "```",
            "",
            "## Available Test Files",
        ]

        for test in test_files[:30]:
            prompt_parts.append(f"- {test}")

        prompt_parts.extend([
            "",
            "## Task",
            "Identify test files that are likely to be affected by these changes.",
            "Consider:",
            "- Direct imports of the changed module",
            "- Tests that exercise the modified functionality",
            "- Integration tests that might depend on this code",
            "",
            "Respond with JSON in this format:",
            "```json",
            "{",
            '  "affected_tests": [',
            '    {"test": "test_file.py", "reason": "Brief reason"}',
            "  ]",
            "}",
            "```",
        ])

        return "\n".join(prompt_parts)

    @staticmethod
    def summarize_results_prompt(
        passed: int,
        failed: int,
        skipped: int,
        failed_tests: list[dict],
        risk_predictions: Optional[list[dict]] = None,
    ) -> str:
        """Generate a prompt to summarize test results.

        Args:
            passed: Number of passed tests
            failed: Number of failed tests
            skipped: Number of skipped tests
            failed_tests: List of failed test info
            risk_predictions: Optional predictions that were made

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "Summarize the following test results and provide insights.",
            "",
            "## Results",
            f"- Passed: {passed}",
            f"- Failed: {failed}",
            f"- Skipped: {skipped}",
        ]

        if failed_tests:
            prompt_parts.extend(["", "## Failed Tests"])
            for test in failed_tests[:10]:
                prompt_parts.append(f"- {test.get('test_name', 'unknown')}")
                if test.get("error_message"):
                    prompt_parts.append(f"  Error: {test['error_message'][:200]}")

        if risk_predictions:
            prompt_parts.extend(["", "## Risk Predictions"])
            for pred in risk_predictions[:10]:
                prompt_parts.append(
                    f"- {pred.get('test_name', '?')} "
                    f"(predicted risk: {pred.get('risk_score', 0):.1%})"
                )

        prompt_parts.extend([
            "",
            "## Task",
            "Provide a brief summary of the test results, including:",
            "- Overall health assessment",
            "- Patterns in failures (if any)",
            "- Accuracy of risk predictions (if available)",
            "- Recommended next steps",
        ])

        return "\n".join(prompt_parts)
