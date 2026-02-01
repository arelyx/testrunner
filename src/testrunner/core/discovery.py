"""Test discovery functionality."""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from testrunner.config import TestRunnerConfig


@dataclass
class DiscoveredTest:
    """Represents a discovered test."""

    name: str
    file_path: str
    line_number: Optional[int] = None
    module: str = ""
    class_name: str = ""
    function_name: str = ""

    @property
    def full_name(self) -> str:
        """Get the full test name including file and function."""
        parts = [self.file_path]
        if self.class_name:
            parts.append(self.class_name)
        if self.function_name:
            parts.append(self.function_name)
        return "::".join(parts)


@dataclass
class DiscoveryResult:
    """Result of test discovery."""

    tests: list[DiscoveredTest] = field(default_factory=list)
    error: Optional[str] = None
    total_count: int = 0

    @property
    def success(self) -> bool:
        """Check if discovery was successful."""
        return self.error is None


class TestDiscovery:
    """Discovers tests in a project."""

    def __init__(self, config: TestRunnerConfig, base_dir: Path):
        """Initialize test discovery."""
        self.config = config
        self.base_dir = base_dir
        self.test_dir = base_dir / config.test.test_directory

    def discover(self) -> DiscoveryResult:
        """Discover all tests in the project."""
        command = self.config.test.command.lower()

        if "pytest" in command:
            return self._discover_pytest()
        else:
            # Generic discovery - just list test files
            return self._discover_generic()

    def _discover_pytest(self) -> DiscoveryResult:
        """Discover tests using pytest's collection."""
        try:
            # Use pytest --collect-only to discover tests
            # Note: -qq (double quiet) needed for line-based output in pytest 9.x
            result = subprocess.run(
                ["pytest", "--collect-only", "-qq", str(self.test_dir)],
                capture_output=True,
                text=True,
                cwd=self.base_dir,
                timeout=60,
            )

            tests = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("=") or "error" in line.lower():
                    continue

                # Parse pytest output format: path/to/test.py::TestClass::test_method
                if "::" in line:
                    parts = line.split("::")
                    file_path = parts[0]

                    class_name = ""
                    function_name = ""

                    if len(parts) >= 3:
                        class_name = parts[1]
                        function_name = parts[2]
                    elif len(parts) == 2:
                        function_name = parts[1]

                    test = DiscoveredTest(
                        name=line,
                        file_path=file_path,
                        class_name=class_name,
                        function_name=function_name,
                    )
                    tests.append(test)

            return DiscoveryResult(
                tests=tests,
                total_count=len(tests),
            )

        except subprocess.TimeoutExpired:
            return DiscoveryResult(error="Test discovery timed out")
        except FileNotFoundError:
            return DiscoveryResult(error="pytest not found. Is it installed?")
        except Exception as e:
            return DiscoveryResult(error=str(e))

    def _discover_generic(self) -> DiscoveryResult:
        """Generic test discovery based on file patterns."""
        tests = []

        if not self.test_dir.exists():
            return DiscoveryResult(
                error=f"Test directory not found: {self.test_dir}"
            )

        # Find test files
        test_patterns = ["test_*.py", "*_test.py"]

        for pattern in test_patterns:
            for test_file in self.test_dir.rglob(pattern):
                relative_path = test_file.relative_to(self.base_dir)
                test = DiscoveredTest(
                    name=str(relative_path),
                    file_path=str(relative_path),
                )
                tests.append(test)

        return DiscoveryResult(
            tests=tests,
            total_count=len(tests),
        )

    def get_test_files(self) -> list[Path]:
        """Get a list of all test files."""
        result = self.discover()
        return list(set(Path(t.file_path) for t in result.tests))
