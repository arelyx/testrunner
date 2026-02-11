"""Prompt templates for LLM interactions."""

from typing import Optional


class PromptTemplates:
    """Collection of prompt templates for test analysis."""

    SYSTEM_PROMPT = """You are an expert software testing assistant. Your role is to:
1. Analyze code changes and predict which tests are likely to be affected
2. Identify potential causes of test failures
3. Provide actionable insights for debugging

Be concise and technical. Focus on practical, specific recommendations.
When providing JSON responses, ensure they are valid and parseable."""

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
