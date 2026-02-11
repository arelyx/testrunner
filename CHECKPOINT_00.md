# CHECKPOINT 00: Initial State Documentation

**Date:** 2026-02-11
**Status:** Starting Point - Before Refactoring

---

## Overview

This checkpoint documents the system state before beginning the language-agnostic refactoring. The current system is tightly coupled to pytest and Python, with unnecessary pre-execution complexity.

---

## System State

### Test Results
```
34 tests passed
0 tests failed
Test suite: PASSING
```

### Current Architecture

**Component Count:**
- Total Python files: 24
- Core modules: 3 (discovery.py, parser.py, runner.py)
- Risk modules: 2 (scorer.py, prioritizer.py)
- LLM modules: 4 (base.py, ollama.py, analysis.py, prompts.py)
- Storage modules: 2 (database.py, models.py)
- Git modules: 2 (diff.py, history.py)

**Lines of Framework-Specific Code:**
- pytest references: 26 occurrences
- Python-specific logic: ~300 lines in parser.py and discovery.py

### Current Execution Flow

```
CLI.run()
  → Git Analysis (optional)
  → Risk Analysis (LLM call to predict failures)
    → Test Discovery (pytest --collect-only)
    → Get historical data
    → LLM risk prediction
  → Execute Tests (pytest with injected flags)
  → Parse Results (pytest-specific parsing)
  → Analyze Failures (LLM call for root cause)
  → Generate Report
```

### Problems Identified

1. **Not Language-Agnostic**
   - `discovery.py`: Hardcoded pytest discovery
   - `parser.py`: 234 lines of pytest-specific parsing
   - `runner.py`: pytest command building logic
   - Fallback parser is naive regex

2. **Unnecessary Pre-Execution Complexity**
   - Risk scoring before tests run (expensive)
   - Requires test discovery phase
   - Value unclear when tests run anyway

3. **Over-Engineered Historical Tracking**
   - Complex aggregation in `test_history` table
   - Flaky test detection
   - Unclear use case for failure analysis tool

4. **Misaligned Value Proposition**
   - Currently: Predict failures, run high-risk first
   - Should be: Run tests, explain failures

---

## Database Schema (Current)

### Tables

**test_runs**
```sql
CREATE TABLE test_runs (
    id INTEGER PRIMARY KEY,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    commit_hash TEXT,
    branch TEXT,
    total_tests INTEGER,
    passed INTEGER,
    failed INTEGER,
    skipped INTEGER
);
```

**test_results**
```sql
CREATE TABLE test_results (
    id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES test_runs(id),
    test_name TEXT,
    test_file TEXT,
    status TEXT,
    duration_ms INTEGER,
    output TEXT,
    error_message TEXT,
    risk_score REAL  -- Will be removed
);
```

**test_history** (Complex, to be removed)
```sql
CREATE TABLE test_history (
    test_name TEXT PRIMARY KEY,
    last_failed_at TIMESTAMP,
    failure_count INTEGER,
    total_runs INTEGER,
    avg_duration_ms REAL
);
```

**risk_analysis** (To be removed)
```sql
CREATE TABLE risk_analysis (
    test_name TEXT PRIMARY KEY,
    risk_score REAL,
    risk_factors TEXT,
    affected_by_changes INTEGER,
    updated_at TIMESTAMP
);
```

---

## Configuration Schema (Current)

```json
{
  "project": {
    "name": "string",
    "language": "python",  // Default to python
    "description": "string"
  },
  "test": {
    "command": "pytest",  // Default to pytest
    "args": ["array"],    // Separate args array
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
  "git": {
    "enabled": true,
    "compare_ref": "HEAD~5",
    "include_uncommitted": true
  },
  "storage": {
    "database_path": ".testrunner/history.db"
  },
  "report": {
    "output_dir": "./reports",
    "filename": "test_report.html",
    "title": "Test Results"
  }
}
```

---

## LLM Usage (Current)

### API Calls Made

1. **Risk Prediction** (During risk analysis phase)
   - Input: Git changes + test files + historical failures
   - Output: `{high_risk_tests: [...], summary: "..."}`
   - Prompt: `PromptTemplates.risk_analysis_prompt()`

2. **Root Cause Analysis** (For failed tests)
   - Input: Test name + error + git changes
   - Output: `{likely_cause: "...", suspected_commit: "...", suggested_fix: "..."}`
   - Prompt: `PromptTemplates.root_cause_prompt()`

3. **Test Impact Analysis** (Unused?)
   - Input: File change + diff + test files
   - Output: `{affected_tests: [...]}`
   - Prompt: `PromptTemplates.test_impact_prompt()`

4. **Results Summary** (Unused?)
   - Input: Test counts + failed tests + risk predictions
   - Output: Summary text
   - Prompt: `PromptTemplates.summarize_results_prompt()`

---

## External Command Executions (Current)

### Git Commands (via GitPython)
- `git diff` - File changes
- `git log` - Commit history
- `git blame` - Attribution

### Test Commands
- `pytest --collect-only -qq` - Discovery phase
- `pytest [args] --json-report --json-report-file=...` - Execution phase

---

## Key Files Analysis

### Most Complex Files

1. **runner.py** (263 lines)
   - Orchestrates entire flow
   - Pytest-specific command building
   - Calls discovery, parser, analyzer

2. **parser.py** (235 lines)
   - 190 lines of pytest parsing
   - JSON parser + stdout parser
   - Weak generic fallback

3. **scorer.py** (287 lines)
   - Complex risk computation
   - Depends on discovery
   - Multiple weight factors

4. **discovery.py** (150 lines)
   - Pytest-specific discovery
   - Generic fallback only finds .py files

### Files to Preserve (Minimal Changes)

- `git/diff.py` - Already language-agnostic
- `git/history.py` - Already language-agnostic
- `llm/base.py` - Good abstraction
- `llm/ollama.py` - Working implementation
- `storage/models.py` - Clean data models
- `report/generator.py` - Jinja2 rendering (needs minor updates)

---

## Fixture Projects (Current)

### Python Calculator
- **Path:** `test_repos/fixture-python-calculator/`
- **Framework:** pytest
- **Tests:** 10 tests (some intentionally failing)
- **Purpose:** Demonstrate failure detection

### Python API
- **Path:** `test_repos/fixture-python-api/`
- **Framework:** pytest
- **Tests:** Multiple passing tests
- **Purpose:** Demonstrate passing suite

**Missing:** JavaScript, Go, Java, Rust examples

---

## Refactoring Plan

### Phase 1: Create New Components
1. `llm/parser.py` - LLM-based test output parser
2. `llm/analyzer.py` - Failure analysis (simplified from analysis.py)
3. `core/executor.py` - Simple test executor

### Phase 2: Update Existing
1. `config.py` - Simplify schema
2. `cli.py` - Use new components
3. `storage/database.py` - Remove history complexity
4. `storage/models.py` - Remove unused models
5. `report/generator.py` - Focus on failures

### Phase 3: Delete Old Code
1. `core/discovery.py`
2. `core/parser.py`
3. `core/runner.py`
4. `risk/scorer.py`
5. `risk/prioritizer.py`

### Phase 4: Add Multi-Language Support
1. JavaScript/Jest fixture
2. Go test fixture
3. Update documentation

---

## Success Criteria

After refactoring, the system should:

1. **Run any test framework** - No pytest-specific code
2. **Parse via LLM** - Single parser for all frameworks
3. **Focus on failures** - Root cause analysis is primary value
4. **Simple architecture** - Fewer moving parts
5. **Pass all tests** - No regressions
6. **Work with fixtures** - Python, JS, Go examples all work

---

## Next Steps

1. Create feature branch for LLM parser
2. Implement `llm/parser.py` with test fixtures
3. Test parser with pytest, Jest, Go output examples
4. Create PR and merge

---

*End of CHECKPOINT_00.md*
