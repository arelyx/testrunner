# TestRunner

Test execution tool with LLM-based output parsing and failure analysis. Works with any test framework (pytest, Jest, JUnit, go test, etc.).

## Installation

```bash
git clone https://github.com/your-org/testrunner.git
cd testrunner
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

This installs testrunner in editable mode, making the `testrunner` command available in your PATH.

**Alternative: Run without installing**

If you don't want to install, you can run it directly:

```bash
python -m testrunner.cli run
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

## Usage

```bash
cd your-project
testrunner run
```

View the generated report at `reports/test_report.html`.

## CLI Commands

### run
Execute tests and generate report.

```bash
testrunner run [--config PATH] [--no-report] [--verbose]
```

Options:
- `--config, -c`: Path to config file (default: testrunner.json)
- `--no-report`: Skip HTML report generation
- `--verbose, -v`: Verbose output

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
testrunner report [--run-id ID]
```

### history
Show test run history.

```bash
testrunner history [--limit N]
```

## Testing

### Running TestRunner's Test Suite

```bash
pytest tests/ -v
pytest tests/ --cov=testrunner
```

### End-to-End Tests

The `test_repos/` directory contains fixture projects for E2E testing:
- `fixture-python-calculator/` - Python/pytest fixture with intentional test failure
- `fixture-javascript-calculator/` - JavaScript/Jest fixture with intentional test failure

Run E2E tests:

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
python -m testrunner.cli run
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
