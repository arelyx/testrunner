"""Tests for the configuration module."""

import json
import tempfile
from pathlib import Path

import pytest

from testrunner.config import (
    TestRunnerConfig,
    ProjectConfig,
    TestConfig,
    LLMConfig,
    get_default_config,
    create_example_config,
)


class TestProjectConfig:
    """Tests for ProjectConfig."""

    def test_default_values(self):
        """Test default values are set correctly."""
        config = ProjectConfig(name="test")
        assert config.name == "test"
        assert config.language == "python"
        assert config.description == ""


class TestTestConfig:
    """Tests for TestConfig."""

    def test_default_values(self):
        """Test default values are set correctly."""
        config = TestConfig()
        assert config.command == "pytest"
        assert config.args == []
        assert config.test_directory == "tests/"
        assert config.timeout_seconds == 300
        assert config.fail_fast is False

    def test_timeout_validation(self):
        """Test that timeout must be positive."""
        with pytest.raises(ValueError):
            TestConfig(timeout_seconds=0)


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_default_values(self):
        """Test default values are set correctly."""
        config = LLMConfig()
        assert config.provider == "ollama"
        assert config.model == "llama3.2"
        assert config.base_url == "http://localhost:11434"

    def test_provider_validation(self):
        """Test that only valid providers are accepted."""
        with pytest.raises(ValueError):
            LLMConfig(provider="invalid")

    def test_provider_case_insensitive(self):
        """Test that provider is case-insensitive."""
        config = LLMConfig(provider="OLLAMA")
        assert config.provider == "ollama"


class TestTestRunnerConfig:
    """Tests for TestRunnerConfig."""

    def test_default_config(self):
        """Test creating a default configuration."""
        config = get_default_config()
        assert config.project.language == "python"
        assert config.test.command == "pytest"
        assert config.llm.provider == "ollama"

    def test_from_file(self):
        """Test loading configuration from a file."""
        config_data = {
            "project": {"name": "test-project", "language": "python"},
            "test": {"command": "pytest", "args": ["-v"]},
            "llm": {"provider": "ollama", "model": "llama3.2"},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()

            config = TestRunnerConfig.from_file(f.name)
            assert config.project.name == "test-project"
            assert config.test.args == ["-v"]

    def test_from_file_not_found(self):
        """Test loading from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            TestRunnerConfig.from_file("/nonexistent/path.json")

    def test_to_file(self):
        """Test saving configuration to a file."""
        config = get_default_config()
        config.project.name = "saved-project"

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            config.to_file(path)

            assert path.exists()

            loaded = TestRunnerConfig.from_file(path)
            assert loaded.project.name == "saved-project"

    def test_create_example_config(self):
        """Test creating an example configuration file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "example.json"
            result = create_example_config(path)

            assert result == path
            assert path.exists()

            with open(path) as f:
                data = json.load(f)
                assert "project" in data
                assert "test" in data
                assert "llm" in data

    def test_get_absolute_paths(self):
        """Test getting absolute paths from config."""
        config = get_default_config()
        config.test.test_directory = "tests/"
        config.report.output_dir = "./reports"

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            paths = config.get_absolute_paths(base_dir)

            assert paths["test_directory"].is_absolute()
            assert str(paths["test_directory"]).endswith("tests")

    def test_get_hints_content(self):
        """Test reading hints file content."""
        config = get_default_config()
        config.hints_file = "HINTS.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            hints_path = base_dir / "HINTS.md"
            hints_path.write_text("# Test Hints\nSome content")

            content = config.get_hints_content(base_dir)
            assert content == "# Test Hints\nSome content"

    def test_get_hints_content_not_found(self):
        """Test getting hints when file doesn't exist."""
        config = get_default_config()
        config.hints_file = "HINTS.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            content = config.get_hints_content(tmpdir)
            assert content is None
