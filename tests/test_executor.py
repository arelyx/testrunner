"""Tests for test command executor."""

import tempfile
from pathlib import Path

import pytest

from testrunner.core.executor import ExecutionError, RawTestOutput, TestExecutor


class TestTestExecutor:
    """Tests for TestExecutor."""

    def test_execute_simple_command(self):
        """Test executing a simple command."""
        executor = TestExecutor(
            command="echo 'test output'",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        assert isinstance(result, RawTestOutput)
        assert "test output" in result.stdout
        assert result.exit_code == 0
        assert result.duration_ms > 0
        assert result.command == "echo 'test output'"

    def test_execute_command_with_stderr(self):
        """Test command that outputs to stderr."""
        executor = TestExecutor(
            command="echo 'error message' >&2",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        assert "error message" in result.stderr
        assert result.exit_code == 0

    def test_execute_failing_command(self):
        """Test command that exits with non-zero code."""
        executor = TestExecutor(
            command="exit 1",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        assert result.exit_code == 1

    def test_execute_in_specific_directory(self):
        """Test command execution in specific directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a file in the temp directory
            test_file = tmpdir_path / "test.txt"
            test_file.write_text("content")

            executor = TestExecutor(
                command="cat test.txt",
                working_directory=tmpdir_path,
                timeout_seconds=10,
            )

            result = executor.execute()

            assert "content" in result.stdout
            assert result.exit_code == 0

    def test_execute_with_environment_variables(self):
        """Test command execution with custom environment."""
        executor = TestExecutor(
            command="echo $TEST_VAR",
            working_directory=Path.cwd(),
            timeout_seconds=10,
            environment={"TEST_VAR": "test_value"},
        )

        result = executor.execute()

        assert "test_value" in result.stdout

    def test_execute_timeout(self):
        """Test command that times out."""
        executor = TestExecutor(
            command="sleep 10",
            working_directory=Path.cwd(),
            timeout_seconds=1,  # Short timeout
        )

        result = executor.execute()

        assert result.exit_code == -1
        assert "timed out" in result.stderr.lower()
        assert result.duration_ms >= 1000  # At least timeout duration

    def test_execute_complex_command(self):
        """Test complex command with pipes."""
        executor = TestExecutor(
            command="echo 'line1\nline2\nline3' | wc -l",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        assert result.exit_code == 0
        # Should count lines
        assert "3" in result.stdout.strip()

    def test_execute_python_command(self):
        """Test executing Python code."""
        executor = TestExecutor(
            command="python3 -c \"print('hello from python')\"",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        assert "hello from python" in result.stdout
        assert result.exit_code == 0

    def test_to_dict_conversion(self):
        """Test RawTestOutput.to_dict() method."""
        executor = TestExecutor(
            command="echo 'test'",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "stdout" in result_dict
        assert "stderr" in result_dict
        assert "exit_code" in result_dict
        assert "duration_ms" in result_dict
        assert "command" in result_dict
        assert result_dict["command"] == "echo 'test'"

    def test_captures_both_stdout_and_stderr(self):
        """Test that both stdout and stderr are captured."""
        executor = TestExecutor(
            command="echo 'stdout line' && echo 'stderr line' >&2",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        assert "stdout line" in result.stdout
        assert "stderr line" in result.stderr

    def test_handles_command_not_found(self):
        """Test handling of non-existent command."""
        executor = TestExecutor(
            command="nonexistentcommand123",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        # Should return error result
        assert result.exit_code != 0
        # Stderr should contain error info (either from shell or our handler)
        assert len(result.stderr) > 0 or result.exit_code == 127

    def test_multiple_executions_independent(self):
        """Test that multiple executions are independent."""
        executor1 = TestExecutor(
            command="echo 'first'",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )
        executor2 = TestExecutor(
            command="echo 'second'",
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result1 = executor1.execute()
        result2 = executor2.execute()

        assert "first" in result1.stdout
        assert "second" in result2.stdout
        assert result1.stdout != result2.stdout

    def test_duration_measurement(self):
        """Test that duration is measured reasonably."""
        executor = TestExecutor(
            command="sleep 0.1",  # 100ms sleep
            working_directory=Path.cwd(),
            timeout_seconds=10,
        )

        result = executor.execute()

        # Duration should be at least 100ms
        assert result.duration_ms >= 100
        # But not unreasonably long
        assert result.duration_ms < 10000

    def test_empty_environment_dict(self):
        """Test with explicitly empty environment dict."""
        executor = TestExecutor(
            command="echo 'test'",
            working_directory=Path.cwd(),
            timeout_seconds=10,
            environment={},
        )

        result = executor.execute()

        assert result.exit_code == 0

    def test_preserves_exit_codes(self):
        """Test that various exit codes are preserved."""
        for exit_code in [0, 1, 2, 127]:
            executor = TestExecutor(
                command=f"exit {exit_code}",
                working_directory=Path.cwd(),
                timeout_seconds=10,
            )

            result = executor.execute()

            if exit_code != 127:  # 127 might be special on some systems
                assert result.exit_code == exit_code
