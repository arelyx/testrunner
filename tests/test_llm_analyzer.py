"""Tests for LLM-based failure analyzer."""

from unittest.mock import Mock

import pytest

from testrunner.llm.analyzer import FailureAnalysis, FailureAnalyzer
from testrunner.storage.models import TestResult, TestStatus


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = Mock()
    client.is_available.return_value = True
    return client


@pytest.fixture
def failed_test_result():
    """Create a sample failed test result."""
    return TestResult(
        test_name="tests/test_calculator.py::test_divide_by_zero",
        test_file="tests/test_calculator.py",
        status=TestStatus.FAILED,
        error_message="""
def test_divide_by_zero():
    calc = Calculator()
>   result = calc.divide(10, 0)
E   ZeroDivisionError: division by zero

tests/test_calculator.py:25: ZeroDivisionError
""",
    )


@pytest.fixture
def git_changes():
    """Create sample git changes."""
    return {
        "files": [
            {
                "path": "src/calculator.py",
                "change_type": "M",
            },
            {
                "path": "tests/test_calculator.py",
                "change_type": "M",
            },
        ],
        "commits": [
            {
                "short_hash": "abc123",
                "message": "Fix division logic",
            },
            {
                "short_hash": "def456",
                "message": "Add validation",
            },
        ],
    }


class TestFailureAnalyzer:
    """Tests for FailureAnalyzer."""

    def test_analyze_with_git_context(
        self, mock_llm_client, failed_test_result, git_changes
    ):
        """Test analyzing failure with git context."""
        mock_llm_client.generate_json.return_value = {
            "likely_cause": "Division by zero not handled",
            "suspected_file": "src/calculator.py",
            "suspected_commit": "abc123",
            "confidence": 0.85,
            "explanation": "The divide method doesn't check for zero divisor",
            "suggested_fix": "Add check: if divisor == 0: raise ValueError('Cannot divide by zero')",
        }

        analyzer = FailureAnalyzer(mock_llm_client)
        result = analyzer.analyze(failed_test_result, git_changes)

        assert isinstance(result, FailureAnalysis)
        assert result.test_name == "tests/test_calculator.py::test_divide_by_zero"
        assert result.likely_cause == "Division by zero not handled"
        assert result.suspected_file == "src/calculator.py"
        assert result.suspected_commit == "abc123"
        assert result.confidence == 0.85
        assert "divide method" in result.explanation
        assert "ValueError" in result.suggested_fix

    def test_analyze_without_git_context(self, mock_llm_client, failed_test_result):
        """Test analyzing failure without git context."""
        mock_llm_client.generate_json.return_value = {
            "likely_cause": "Missing error handling",
            "suspected_file": None,
            "suspected_commit": None,
            "confidence": 0.6,
            "explanation": "Test expects error handling that doesn't exist",
            "suggested_fix": "Implement zero division check",
        }

        analyzer = FailureAnalyzer(mock_llm_client)
        result = analyzer.analyze(failed_test_result, git_changes=None)

        assert result is not None
        assert result.suspected_file is None
        assert result.suspected_commit is None
        assert result.confidence == 0.6

    def test_analyze_when_llm_unavailable(self, failed_test_result):
        """Test behavior when LLM is unavailable."""
        mock_client = Mock()
        mock_client.is_available.return_value = False

        analyzer = FailureAnalyzer(mock_client)
        result = analyzer.analyze(failed_test_result)

        assert result is None

    def test_analyze_when_llm_errors(self, mock_llm_client, failed_test_result):
        """Test handling of LLM errors."""
        mock_llm_client.generate_json.side_effect = Exception("LLM error")

        analyzer = FailureAnalyzer(mock_llm_client)
        result = analyzer.analyze(failed_test_result)

        assert result is None  # Should return None on error

    def test_analyze_without_error_message(self, mock_llm_client):
        """Test analyzing test without error message."""
        test_without_error = TestResult(
            test_name="test_something",
            test_file="test.py",
            status=TestStatus.FAILED,
            error_message="",  # No error message
        )

        analyzer = FailureAnalyzer(mock_llm_client)
        result = analyzer.analyze(test_without_error)

        assert result is None  # Can't analyze without error message

    def test_analyze_multiple_failures(self, mock_llm_client):
        """Test analyzing multiple failures at once."""
        test1 = TestResult(
            test_name="test1",
            test_file="test.py",
            status=TestStatus.FAILED,
            error_message="Error 1",
        )
        test2 = TestResult(
            test_name="test2",
            test_file="test.py",
            status=TestStatus.FAILED,
            error_message="Error 2",
        )

        mock_llm_client.generate_json.side_effect = [
            {
                "likely_cause": "Cause 1",
                "suspected_file": None,
                "suspected_commit": None,
                "confidence": 0.7,
                "explanation": "Explanation 1",
                "suggested_fix": "Fix 1",
            },
            {
                "likely_cause": "Cause 2",
                "suspected_file": None,
                "suspected_commit": None,
                "confidence": 0.8,
                "explanation": "Explanation 2",
                "suggested_fix": "Fix 2",
            },
        ]

        analyzer = FailureAnalyzer(mock_llm_client)
        results = analyzer.analyze_multiple([test1, test2])

        assert len(results) == 2
        assert results[0].test_name == "test1"
        assert results[1].test_name == "test2"
        assert results[0].likely_cause == "Cause 1"
        assert results[1].likely_cause == "Cause 2"

    def test_prompt_building(self, mock_llm_client, failed_test_result, git_changes):
        """Test that analysis prompt is built correctly."""
        analyzer = FailureAnalyzer(mock_llm_client)
        prompt = analyzer._build_analysis_prompt(failed_test_result, git_changes)

        # Check prompt contains key information
        assert "test_divide_by_zero" in prompt
        assert "ZeroDivisionError" in prompt
        assert "src/calculator.py" in prompt  # From git changes
        assert "abc123" in prompt  # Commit hash
        assert "Fix division logic" in prompt  # Commit message
        assert "JSON" in prompt

    def test_prompt_without_git_context(self, mock_llm_client, failed_test_result):
        """Test prompt building without git context."""
        analyzer = FailureAnalyzer(mock_llm_client)
        prompt = analyzer._build_analysis_prompt(failed_test_result, git_changes=None)

        # Should still have test info
        assert "test_divide_by_zero" in prompt
        assert "ZeroDivisionError" in prompt
        # Should not have git info
        assert "Recently Changed Files" not in prompt
        assert "Recent Commits" not in prompt

    def test_to_dict_conversion(self):
        """Test FailureAnalysis.to_dict() method."""
        analysis = FailureAnalysis(
            test_name="test1",
            likely_cause="The cause",
            suspected_file="file.py",
            suspected_commit="abc123",
            confidence=0.9,
            explanation="Explanation",
            suggested_fix="Fix",
        )

        result_dict = analysis.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["test_name"] == "test1"
        assert result_dict["likely_cause"] == "The cause"
        assert result_dict["suspected_file"] == "file.py"
        assert result_dict["suspected_commit"] == "abc123"
        assert result_dict["confidence"] == 0.9

    def test_handles_llm_response_with_missing_fields(self, mock_llm_client, failed_test_result):
        """Test handling LLM response with missing optional fields."""
        mock_llm_client.generate_json.return_value = {
            "likely_cause": "Something broke",
            # Missing other fields
        }

        analyzer = FailureAnalyzer(mock_llm_client)
        result = analyzer.analyze(failed_test_result)

        assert result is not None
        assert result.likely_cause == "Something broke"
        assert result.suspected_file is None
        assert result.confidence == 0.5  # Default value

    def test_truncates_long_error_messages(self, mock_llm_client):
        """Test that very long error messages are truncated."""
        long_error = "x" * 10000
        test_with_long_error = TestResult(
            test_name="test",
            test_file="test.py",
            status=TestStatus.FAILED,
            error_message=long_error,
        )

        analyzer = FailureAnalyzer(mock_llm_client)
        prompt = analyzer._build_analysis_prompt(test_with_long_error, None)

        # Error should be truncated to 5000 chars
        assert len(prompt) < len(long_error)

    def test_limits_git_changes_in_prompt(self, mock_llm_client, failed_test_result):
        """Test that git changes are limited in prompt."""
        many_files = {
            "files": [{"path": f"file{i}.py", "change_type": "M"} for i in range(50)],
            "commits": [
                {"short_hash": f"hash{i}", "message": f"Commit {i}"}
                for i in range(50)
            ],
        }

        analyzer = FailureAnalyzer(mock_llm_client)
        prompt = analyzer._build_analysis_prompt(failed_test_result, many_files)

        # Should be limited (15 files, 10 commits)
        file_count = prompt.count("file")
        assert file_count <= 20  # Reasonable limit including word "file" in text
