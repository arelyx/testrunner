# TestRunner

Test execution tool with LLM-based output parsing and failure analysis. Works with any test framework (pytest, Jest, JUnit, go test, etc.).

## Installation

```bash
git clone https://github.com/arelyx/testrunner.git
cd testrunner
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

This installs testrunner in editable mode, making the `testrunner` command available in your PATH.

**Alternative: Run without installing**

If you don't want to install, you can run it directly:

```bash
python -m testrunner run
```

## Requirements

- Python 3.10+
- Ollama instance with a model (e.g., llama3.2)
- Git

## Configuration

Create `testrunner.json` in your project root:

```json
{
  "project": {
    "name": "my-project",
    "language": "python",
    "description": "Optional context for LLM"
  },
  "test": {
    "command": "pytest -v --tb=short",
    "working_directory": ".",
    "timeout_seconds": 300
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
    "filename": "test_report.html"
  },
  "storage": {
    "database_path": ".testrunner/history.db"
  }
}
```

### Configuration Examples

**Python (pytest)**
```json
{
  "test": {
    "command": "pytest -v --tb=short",
    "working_directory": "."
  }
}
```

**JavaScript (Jest)**
```json
{
  "test": {
    "command": "npm test",
    "working_directory": "."
  }
}
```

**Go**
```json
{
  "test": {
    "command": "go test -v ./...",
    "working_directory": "."
  }
}
```

**Rust**
```json
{
  "test": {
    "command": "cargo test",
    "working_directory": "."
  }
}
```

**Java (Maven)**
```json
{
  "test": {
    "command": "mvn test",
    "working_directory": "."
  }
}
```

### HINTS.md

You can create a `HINTS.md` file in your project root to provide additional context to the LLM for better failure analysis. This file can include project architecture, known flaky tests, critical paths, and test dependencies. See `HINTS.md.example` for a template.

## Usage

```bash
cd your-project
testrunner run
```

View the generated report at `reports/test_report.html`.

## CLI Commands

Global options (apply to all commands):

- `--config, -c`: Path to config file (default: testrunner.json)
- `--verbose, -v`: Verbose output

### run

Execute tests and generate report.

```bash
testrunner [--config PATH] [--verbose] run [--no-report]
```

Options:

- `--no-report`: Skip HTML report generation

### init

Generate example configuration.

```bash
testrunner init [--output PATH] [--force]
```

Options:

- `--output, -o`: Output path (default: testrunner.json)
- `--force, -f`: Overwrite existing file

### report

Generate report from previous run.

```bash
testrunner [--config PATH] report [--run-id ID]
```

### history

Show test run history.

```bash
testrunner [--config PATH] history [--limit N]
```

## Testing

### Running TestRunner's Test Suite

```bash
pytest tests/ -v
pytest tests/ --cov=testrunner
```

### End-to-End Tests

The `test_repos/` directory contains fixture projects for E2E testing:

- `fixture-python-calculator/` - Python/pytest fixture with intentional divide-by-zero failure
- `fixture-python-api/` - Flask API with intentional duplicate email validation bug
- `fixture-javascript-calculator/` - JavaScript/Jest fixture with intentional divide-by-zero failure

Run the automated E2E test suite:

```bash
python scripts/e2e_test.py
```

Or run fixtures individually:

```bash
# Python fixture
cd test_repos/fixture-python-calculator
testrunner run

# JavaScript fixture (requires npm install first)
cd test_repos/fixture-javascript-calculator
npm install
testrunner run
```

If not installed with `pip install -e .`, use:

```bash
python -m testrunner run
```

These fixtures test:

- Test execution across different languages
- LLM-based output parsing
- Failure analysis with git context
- Report generation

## Development

### Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
pip install pytest pytest-cov black ruff mypy
```

### Code Quality

```bash
black src/ tests/
ruff check src/ tests/
mypy src/
```

## Docker

### Build

```bash
docker-compose build
```

### Run

```bash
TARGET_REPO=/path/to/project docker-compose run testrunner run
```

### Environment Variables

| Variable | Default |
|----------|---------|
| OLLAMA_HOST | http://host.docker.internal:11434 |
| TARGET_REPO | . |
| REPORTS_DIR | ./reports |
