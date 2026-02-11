"""Tests for LLM-based test output parser."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from testrunner.llm.parser import LLMOutputParser, ParsedTestOutput
from testrunner.storage.models import TestStatus


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = Mock()
    client.is_available.return_value = True
    return client


@pytest.fixture
def pytest_output():
    """Load pytest fixture output."""
    fixture_path = Path(__file__).parent / "fixtures" / "pytest_output.txt"
    return fixture_path.read_text()


@pytest.fixture
def jest_output():
    """Load Jest fixture output."""
    fixture_path = Path(__file__).parent / "fixtures" / "jest_output.txt"
    return fixture_path.read_text()


@pytest.fixture
def go_test_output():
    """Load Go test fixture output."""
    fixture_path = Path(__file__).parent / "fixtures" / "go_test_output.txt"
    return fixture_path.read_text()


class TestLLMOutputParser:
    """Tests for LLMOutputParser."""

    def test_parse_pytest_output(self, mock_llm_client, pytest_output):
        """Test parsing pytest output."""
        # Mock LLM response
        mock_llm_client.generate_json.return_value = {
            "tests": [
                {
                    "name": "tests/test_calculator.py::test_add",
                    "file": "tests/test_calculator.py",
                    "status": "passed",
                    "duration_ms": 1,
                    "error_message": None,
                },
                {
                    "name": "tests/test_calculator.py::test_divide_by_zero",
                    "file": "tests/test_calculator.py",
                    "status": "failed",
                    "duration_ms": 2,
                    "error_message": "ZeroDivisionError: division by zero",
                },
                {
                    "name": "tests/test_api.py::test_delete_user",
                    "file": "tests/test_api.py",
                    "status": "skipped",
                    "duration_ms": 0,
                    "error_message": None,
                },
            ],
            "summary": {
                "total": 10,
                "passed": 7,
                "failed": 2,
                "skipped": 1,
                "duration_ms": 840,
            },
        }

        parser = LLMOutputParser(mock_llm_client)
        result = parser.parse(
            stdout=pytest_output,
            stderr="",
            exit_code=1,
            test_command="pytest -v",
            language="python",
        )

        assert isinstance(result, ParsedTestOutput)
        assert result.total == 10
        assert result.passed == 7
        assert result.failed == 2
        assert result.skipped == 1
        assert len(result.tests) == 3

        # Check first test
        first_test = result.tests[0]
        assert first_test.test_name == "tests/test_calculator.py::test_add"
        assert first_test.status == TestStatus.PASSED

        # Check failed test
        failed_test = result.tests[1]
        assert failed_test.status == TestStatus.FAILED
        assert "ZeroDivisionError" in failed_test.error_message

    def test_parse_jest_output(self, mock_llm_client, jest_output):
        """Test parsing Jest output."""
        mock_llm_client.generate_json.return_value = {
            "tests": [
                {
                    "name": "Calculator › adds two numbers correctly",
                    "file": "src/utils/calculator.test.js",
                    "status": "passed",
                    "duration_ms": 3,
                    "error_message": None,
                },
                {
                    "name": "User API › POST /api/users creates user",
                    "file": "src/api/users.test.js",
                    "status": "failed",
                    "duration_ms": 23,
                    "error_message": "expect(received).toBe(expected)\nExpected: 201\nReceived: 500",
                },
            ],
            "summary": {
                "total": 10,
                "passed": 7,
                "failed": 2,
                "skipped": 1,
                "duration_ms": 2341,
            },
        }

        parser = LLMOutputParser(mock_llm_client)
        result = parser.parse(
            stdout=jest_output,
            stderr="",
            exit_code=1,
            test_command="npm test",
            language="javascript",
        )

        assert result.total == 10
        assert result.passed == 7
        assert result.failed == 2
        assert len(result.tests) == 2

        # Check Jest test name format
        assert "Calculator" in result.tests[0].test_name

    def test_parse_go_output(self, mock_llm_client, go_test_output):
        """Test parsing Go test output."""
        mock_llm_client.generate_json.return_value = {
            "tests": [
                {
                    "name": "TestAdd",
                    "file": "calculator_test.go",
                    "status": "passed",
                    "duration_ms": 0,
                    "error_message": None,
                },
                {
                    "name": "TestDivideByZero",
                    "file": "calculator_test.go",
                    "status": "failed",
                    "duration_ms": 0,
                    "error_message": "Expected error but got none",
                },
                {
                    "name": "TestParseQuery",
                    "file": "parser_test.go",
                    "status": "skipped",
                    "duration_ms": 0,
                    "error_message": None,
                },
            ],
            "summary": {
                "total": 8,
                "passed": 5,
                "failed": 2,
                "skipped": 1,
                "duration_ms": 234,
            },
        }

        parser = LLMOutputParser(mock_llm_client)
        result = parser.parse(
            stdout=go_test_output,
            stderr="",
            exit_code=1,
            test_command="go test ./...",
            language="go",
        )

        assert result.total == 8
        assert result.failed == 2
        assert result.skipped == 1

    def test_fallback_parser_when_llm_unavailable(self, pytest_output):
        """Test fallback parser when LLM is unavailable."""
        mock_client = Mock()
        mock_client.is_available.return_value = False

        parser = LLMOutputParser(mock_client)
        result = parser.parse(
            stdout=pytest_output,
            stderr="",
            exit_code=1,
        )

        # Fallback should still provide basic stats
        assert result.total > 0
        assert result.parse_confidence < 1.0  # Low confidence
        assert len(result.tests) == 0  # Can't extract individual tests

    def test_fallback_parser_on_llm_error(self, mock_llm_client, pytest_output):
        """Test fallback when LLM raises exception."""
        mock_llm_client.generate_json.side_effect = Exception("LLM error")

        parser = LLMOutputParser(mock_llm_client)
        result = parser.parse(
            stdout=pytest_output,
            stderr="",
            exit_code=1,
        )

        # Should fallback gracefully
        assert isinstance(result, ParsedTestOutput)
        assert result.parse_confidence < 1.0

    def test_prompt_building(self, mock_llm_client):
        """Test that parsing prompt is built correctly."""
        parser = LLMOutputParser(mock_llm_client)

        prompt = parser._build_parse_prompt(
            stdout="test output",
            stderr="error output",
            exit_code=1,
            test_command="pytest -v",
            language="python",
        )

        # Check prompt contains key information
        assert "test output" in prompt
        assert "error output" in prompt
        assert "pytest -v" in prompt
        assert "python" in prompt
        assert "Exit code: 1" in prompt
        assert "JSON" in prompt

    def test_handles_empty_output(self, mock_llm_client):
        """Test parsing empty output."""
        mock_llm_client.generate_json.return_value = {
            "tests": [],
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "duration_ms": 0,
            },
        }

        parser = LLMOutputParser(mock_llm_client)
        result = parser.parse(
            stdout="",
            stderr="",
            exit_code=0,
        )

        assert result.total == 0
        assert len(result.tests) == 0

    def test_handles_malformed_llm_response(self, mock_llm_client):
        """Test handling of malformed LLM response."""
        mock_llm_client.generate_json.return_value = {
            "tests": [
                {"name": "test1"},  # Missing required fields
            ],
            # Missing summary
        }

        parser = LLMOutputParser(mock_llm_client)
        result = parser.parse(
            stdout="some output",
            stderr="",
            exit_code=0,
        )

        # Should handle gracefully
        assert isinstance(result, ParsedTestOutput)
        assert len(result.tests) >= 0

    def test_truncates_long_output(self, mock_llm_client):
        """Test that very long output is truncated."""
        long_output = "x" * 20000  # Exceeds max length

        parser = LLMOutputParser(mock_llm_client)
        prompt = parser._build_parse_prompt(
            stdout=long_output,
            stderr="",
            exit_code=0,
            test_command=None,
            language=None,
        )

        # Should be truncated
        assert len(prompt) < len(long_output)
        assert "truncated" in prompt

    def test_to_dict_conversion(self, mock_llm_client):
        """Test ParsedTestOutput.to_dict() method."""
        mock_llm_client.generate_json.return_value = {
            "tests": [
                {
                    "name": "test1",
                    "file": "test.py",
                    "status": "passed",
                    "duration_ms": 10,
                    "error_message": None,
                }
            ],
            "summary": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "duration_ms": 10,
            },
        }

        parser = LLMOutputParser(mock_llm_client)
        result = parser.parse(stdout="output", stderr="", exit_code=0)

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "tests" in result_dict
        assert "total" in result_dict
        assert "passed" in result_dict
        assert result_dict["total"] == 1
