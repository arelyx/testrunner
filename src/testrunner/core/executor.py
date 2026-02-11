"""Simple test command executor.

This module provides a straightforward test execution wrapper that runs
any test command and captures its output, without framework-specific logic.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RawTestOutput:
    """Raw output from test command execution."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    command: str

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "command": self.command,
        }


class TestExecutor:
    """Executes test commands and captures output."""

    def __init__(
        self,
        command: str,
        working_directory: Path,
        timeout_seconds: int = 300,
        environment: Optional[dict[str, str]] = None,
    ):
        """Initialize test executor.

        Args:
            command: The test command to execute (e.g., "pytest -v", "npm test")
            working_directory: Directory to run command in
            timeout_seconds: Maximum time to allow for execution
            environment: Additional environment variables to set
        """
        self.command = command
        self.working_directory = working_directory
        self.timeout_seconds = timeout_seconds
        self.environment = environment or {}

    def execute(self) -> RawTestOutput:
        """Execute the test command and capture output.

        Returns:
            RawTestOutput with stdout, stderr, exit code, and duration

        Raises:
            subprocess.TimeoutExpired: If execution exceeds timeout
            subprocess.CalledProcessError: If command fails to run
        """
        # Build environment
        env = {**os.environ, **self.environment}

        # Record start time
        start_time = time.time()

        try:
            # Run command with shell=True to support complex commands
            result = subprocess.run(
                self.command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.working_directory,
                timeout=self.timeout_seconds,
                env=env,
            )

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            return RawTestOutput(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                command=self.command,
            )

        except subprocess.TimeoutExpired:
            # Execution timed out
            duration_ms = self.timeout_seconds * 1000

            return RawTestOutput(
                stdout="",
                stderr=f"Test execution timed out after {self.timeout_seconds} seconds",
                exit_code=-1,
                duration_ms=duration_ms,
                command=self.command,
            )

        except Exception as e:
            # Other execution errors
            duration_ms = int((time.time() - start_time) * 1000)

            return RawTestOutput(
                stdout="",
                stderr=f"Error executing test command: {str(e)}",
                exit_code=-1,
                duration_ms=duration_ms,
                command=self.command,
            )


class ExecutionError(Exception):
    """Raised when test execution fails."""

    pass
