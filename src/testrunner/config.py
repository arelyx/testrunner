"""Configuration management for TestRunner."""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ProjectConfig(BaseModel):
    """Project identification and metadata."""

    name: str = Field(description="Project name for identification")
    language: Optional[str] = Field(default=None, description="Programming language hint for LLM (optional)")
    description: str = Field(default="", description="Brief description for LLM context")


class TestConfig(BaseModel):
    """Test execution configuration."""

    command: str = Field(default="pytest -v", description="Complete test command to execute (e.g., 'pytest -v', 'npm test')")
    working_directory: str = Field(default=".", description="Directory to run command in")
    timeout_seconds: int = Field(default=300, description="Test execution timeout")
    environment: dict[str, str] = Field(default_factory=dict, description="Additional environment variables")

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Timeout must be at least 1 second")
        return v

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Test command cannot be empty")
        return v


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = Field(default="ollama", description="LLM provider (ollama, openrouter)")
    model: str = Field(default="llama3.2", description="Model name to use")
    base_url: str = Field(
        default="http://localhost:11434", description="LLM service base URL"
    )
    timeout_seconds: int = Field(default=120, description="LLM request timeout")
    api_key_env: Optional[str] = Field(
        default=None,
        description="Environment variable name containing the API key (e.g. OPENROUTER_API_KEY)",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"ollama", "openrouter"}
        if v.lower() not in allowed:
            raise ValueError(f"Provider must be one of: {allowed}")
        return v.lower()


class ReportConfig(BaseModel):
    """Report generation configuration."""

    output_dir: str = Field(default="./reports", description="Directory for report output")
    filename: str = Field(default="test_report.html", description="Report filename")
    title: str = Field(default="Test Results", description="Report title")


class GitConfig(BaseModel):
    """Git integration configuration."""

    enabled: bool = Field(default=True, description="Enable git analysis")
    compare_ref: str = Field(default="HEAD~5", description="Git ref to compare against")
    include_uncommitted: bool = Field(default=True, description="Include uncommitted changes")
    ignore_untracked: bool = Field(default=False, description="Exclude untracked files from reports")


class TestRunnerConfig(BaseModel):
    """Main configuration for TestRunner."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    test: TestConfig = Field(default_factory=TestConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    hints_file: str = Field(default="HINTS.md", description="Path to hints file")
    report: ReportConfig = Field(default_factory=ReportConfig)
    git: GitConfig = Field(default_factory=GitConfig)

    @classmethod
    def from_file(cls, path: Path | str) -> "TestRunnerConfig":
        """Load configuration from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        return cls.model_validate(data)

    @classmethod
    def find_and_load(cls, start_dir: Path | str | None = None) -> "TestRunnerConfig":
        """Find and load configuration file, searching up the directory tree."""
        if start_dir is None:
            start_dir = Path.cwd()
        else:
            start_dir = Path(start_dir)

        config_names = ["testrunner.json", ".testrunner.json"]

        # Search up the directory tree
        current = start_dir.resolve()
        while current != current.parent:
            for name in config_names:
                config_path = current / name
                if config_path.exists():
                    return cls.from_file(config_path)
            current = current.parent

        # Check root as well
        for name in config_names:
            config_path = current / name
            if config_path.exists():
                return cls.from_file(config_path)

        raise FileNotFoundError(
            f"No configuration file found. Create testrunner.json or run 'testrunner init'"
        )

    def to_file(self, path: Path | str) -> None:
        """Save configuration to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)

    def get_hints_content(self, base_dir: Path | str | None = None) -> Optional[str]:
        """Read and return the hints file content if it exists."""
        if base_dir is None:
            base_dir = Path.cwd()
        else:
            base_dir = Path(base_dir)

        hints_path = base_dir / self.hints_file
        if hints_path.exists():
            return hints_path.read_text()
        return None

    def get_absolute_paths(self, base_dir: Path | str | None = None) -> dict[str, Path]:
        """Get absolute paths for various config paths."""
        if base_dir is None:
            base_dir = Path.cwd()
        else:
            base_dir = Path(base_dir)

        return {
            "working_directory": (base_dir / self.test.working_directory).resolve(),
            "hints_file": (base_dir / self.hints_file).resolve(),
            "report_output_dir": (base_dir / self.report.output_dir).resolve(),
        }


def get_default_config() -> TestRunnerConfig:
    """Return a default configuration."""
    return TestRunnerConfig(
        project=ProjectConfig(name="my-project", language=None),
        test=TestConfig(command="pytest -v --tb=short", working_directory="."),
        llm=LLMConfig(provider="ollama", model="llama3.2"),
    )


def create_example_config(output_path: Path | str) -> Path:
    """Create an example configuration file."""
    output_path = Path(output_path)
    config = get_default_config()
    config.project.description = "Brief description of your project for LLM context"
    config.to_file(output_path)
    return output_path
