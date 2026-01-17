# TestRunner

An LLM-driven CI system that predicts which tests are likely to fail based on code changes, runs high-risk tests first, identifies which commit caused failures, and publishes a static visual report.

## Features

- **Intelligent Test Prioritization**: Uses LLM analysis combined with historical failure data to predict which tests are most likely to fail
- **Git Integration**: Analyzes code changes to identify affected tests
- **Risk Scoring**: Combines multiple signals (LLM inference, historical failures, file proximity) to compute risk scores
- **Root Cause Analysis**: LLM-powered analysis to identify which commit or code change caused test failures
- **Static Reports**: Generates beautiful HTML reports that can be viewed directly in a browser
- **Ollama Integration**: Works with your existing Ollama instance for LLM capabilities

## Quick Start

### Prerequisites

- Python 3.10+
- An Ollama instance running with a model (e.g., llama3.2)
- Git (for version control analysis)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/testrunner.git
cd testrunner

# Install in development mode
pip install -e .

# Or install dependencies directly
pip install -r requirements.txt
```

### Basic Usage

1. **Initialize configuration** in your project:

```bash
cd your-project
testrunner init
```

This creates a `testrunner.json` configuration file.

2. **Configure your Ollama instance** in `testrunner.json`:

```json
{
  "llm": {
    "provider": "ollama",
    "model": "llama3.2",
    "base_url": "http://localhost:11434",
    "timeout_seconds": 120
  }
}
```

3. **Run tests**:

```bash
testrunner run
```

4. **View the report** - Open `reports/test_report.html` in your browser.

## Configuration

### testrunner.json

```json
{
  "project": {
    "name": "my-project",
    "language": "python",
    "description": "Brief description for LLM context"
  },
  "test": {
    "command": "pytest",
    "args": ["-v", "--tb=short"],
    "test_directory": "tests/",
    "timeout_seconds": 300,
    "fail_fast": false
  },
  "llm": {
    "provider": "ollama",
    "model": "llama3.2",
    "base_url": "http://localhost:11434",
    "timeout_seconds": 120
  },
  "hints_file": "HINTS.md",
  "report": {
    "output_dir": "./reports",
    "filename": "test_report.html",
    "title": "Test Results"
  },
  "git": {
    "enabled": true,
    "compare_ref": "HEAD~5",
    "include_uncommitted": true
  },
  "storage": {
    "database_path": ".testrunner/history.db"
  }
}
```

### Configuration Options

| Section | Option | Description | Default |
|---------|--------|-------------|---------|
| project.name | Project name | Identifier for your project | - |
| project.language | Language | Primary language (for LLM context) | python |
| test.command | Test command | Command to run tests | pytest |
| test.args | Arguments | Arguments for test command | [] |
| test.test_directory | Test directory | Where tests are located | tests/ |
| test.timeout_seconds | Timeout | Max test execution time | 300 |
| test.fail_fast | Fail fast | Stop on first failure | false |
| llm.provider | LLM provider | Currently only "ollama" | ollama |
| llm.model | Model name | Ollama model to use | llama3.2 |
| llm.base_url | Ollama URL | URL of your Ollama instance | http://localhost:11434 |
| git.enabled | Enable git | Enable git analysis | true |
| git.compare_ref | Compare ref | Git ref to compare against | HEAD~5 |

### HINTS.md

Create a `HINTS.md` file in your project root to provide additional context to the LLM:

```markdown
# Project Hints

## Overview
Describe your project's architecture and important components.

## Critical Paths
- `src/auth/` - Authentication, changes affect many tests
- `src/api/` - API endpoints

## Known Flaky Tests
- `tests/test_network.py::test_timeout` - Network timing issues

## Test Dependencies
- Tests require a running database
- Mock services are used for external APIs
```

## CLI Commands

### testrunner init

Initialize a new configuration file.

```bash
testrunner init [--output FILE] [--force]
```

Options:
- `--output, -o`: Output path (default: testrunner.json)
- `--force, -f`: Overwrite existing configuration

### testrunner run

Execute tests with intelligent prioritization.

```bash
testrunner run [OPTIONS]
```

Options:
- `--config, -c`: Path to configuration file
- `--priority-only`: Only run high-priority tests
- `--skip-llm`: Skip LLM analysis (use historical data only)
- `--no-report`: Don't generate HTML report
- `--verbose, -v`: Enable verbose output

### testrunner report

Generate or regenerate a test report.

```bash
testrunner report [--run-id ID]
```

Options:
- `--run-id`: Generate report for specific run (default: latest)

### testrunner history

Show test run history.

```bash
testrunner history [--limit N]
```

Options:
- `--limit, -n`: Number of runs to show (default: 10)

## Docker Usage

### Using Docker Compose

```bash
# Build the image
docker-compose build

# Run tests in your project
TARGET_REPO=/path/to/your/project docker-compose run testrunner run

# Or with environment variables
export OLLAMA_HOST=http://your-ollama-server:11434
docker-compose run testrunner run
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| OLLAMA_HOST | Ollama instance URL | http://host.docker.internal:11434 |
| TARGET_REPO | Path to target repository | Current directory |
| REPORTS_DIR | Output directory for reports | ./reports |

## Sample Projects

The `test_repos/` directory contains sample projects for testing:

### python_calculator

A simple calculator module with an intentional bug (division by zero not handled).

```bash
cd test_repos/python_calculator
testrunner run
```

The `test_divide_by_zero` test will fail, demonstrating:
- Failure detection
- Risk scoring
- Root cause analysis

### python_api

A Flask REST API with comprehensive tests. All tests should pass.

```bash
cd test_repos/python_api
pip install flask
testrunner run
```

## How It Works

### Phase 1: Analysis

1. Load configuration and hints
2. Discover tests using the configured test command
3. Analyze git changes (modified files, recent commits)
4. Query LLM for risk predictions based on:
   - Code changes
   - Project hints
   - Historical failure data

### Phase 2: Execution

1. Compute risk scores combining:
   - LLM predictions
   - Historical failure rates
   - File proximity to changes
2. Prioritize tests by risk score
3. Execute tests (high-risk first if configured)
4. Parse results and store in database

### Phase 3: Reporting

1. For failed tests, perform root cause analysis via LLM
2. Generate static HTML report with:
   - Test results summary
   - High-risk test predictions
   - Root cause analysis
   - Git change information

## Development

### Setup Development Environment

```bash
# Clone the repo
git clone https://github.com/your-org/testrunner.git
cd testrunner

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run testrunner's own tests
pytest tests/

# With coverage
pytest tests/ --cov=testrunner
```

### Code Style

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Architecture

```
testrunner/
├── src/testrunner/
│   ├── cli.py           # Command-line interface
│   ├── config.py        # Configuration management
│   ├── core/            # Test execution
│   │   ├── runner.py    # Main test orchestration
│   │   ├── discovery.py # Test discovery
│   │   └── parser.py    # Result parsing
│   ├── git/             # Git integration
│   │   ├── diff.py      # Diff analysis
│   │   └── history.py   # Commit history
│   ├── llm/             # LLM integration
│   │   ├── ollama.py    # Ollama client
│   │   ├── prompts.py   # Prompt templates
│   │   └── analysis.py  # Test analysis
│   ├── risk/            # Risk scoring
│   │   ├── scorer.py    # Score computation
│   │   └── prioritizer.py # Test prioritization
│   ├── storage/         # Persistence
│   │   ├── database.py  # SQLite operations
│   │   └── models.py    # Data models
│   └── report/          # Report generation
│       ├── generator.py # HTML generation
│       └── templates/   # Jinja2 templates
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests.
