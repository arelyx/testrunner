# TestRunner - System Documentation

**Last Updated:** 2026-02-11
**Version:** 0.1.0

**Note:** This file is maintained by Claude to preserve architectural context between sessions. As the codebase evolves, this documentation will be updated to reflect current state.

---

## Project Mission & Direction

### Core Value Proposition
TestRunner's primary value is **post-test-run failure analysis**. After a test suite runs (which is cheap), provide LLM-powered analysis of what failed and why (expensive but valuable).

### Key Principles from Design Discussion

1. **No pre-execution risk prediction** - Running tests is cheap, LLM calls are expensive. Don't predict failures before running tests.

2. **Language-agnostic architecture** - Must work with ANY test framework (pytest, Jest, JUnit, Go test, cargo test, etc.) without hardcoding parsers.

3. **LLM as universal adapter** - The LLM parses test output from any framework and analyzes failures. Trust the LLM to understand different formats.

4. **Failure analysis focus** - Reports should prominently show failures and LLM-generated explanations of root causes.

5. **Minimal historical data** - Historical test run tracking adds complexity without clear value. Keep it simple.

6. **No backwards compatibility concerns** - This is research-stage software. Optimize for correctness and simplicity.

---

## Current Architecture (Before Refactoring)

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                             │
│                    (cli.py:main, run)                        │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────┐
│ Git Analysis │    │   Test Runner    │    │  Database   │
│  (git/diff)  │    │  (core/runner)   │    │  (storage)  │
└──────────────┘    └──────────────────┘    └─────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Discovery  │    │    Parser    │    │ Risk Scorer  │
│ (discovery)  │    │   (parser)   │    │   (scorer)   │
└──────────────┘    └──────────────┘    └──────────────┘
        │                    │                    │
        └────────────────────┴────────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   LLM Analysis   │
                    │  (llm/analysis)  │
                    └──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Report Generator│
                    │     (report)     │
                    └──────────────────┘
```

### Current Execution Flow (Sequence Diagram)

```
User → CLI.run()
    │
    ├─> Config.find_and_load() → testrunner.json
    │
    ├─> Database.__init__() → .testrunner/history.db
    │
    ├─> TestRunner.__init__(config, db, base_dir)
    │
    ├─> [PHASE 1: Git Analysis]
    │   └─> GitDiffAnalyzer.analyze()
    │       ├─> git.Repo.head.commit.diff()  [EXTERNAL: git command]
    │       ├─> git.Repo.index.diff()        [EXTERNAL: git command]
    │       └─> Returns: {files: [...], commits: [...]}
    │
    ├─> [PHASE 2: Risk Analysis]
    │   └─> TestRunner.analyze_risks()
    │       ├─> RiskScorer.__init__(config, db)
    │       ├─> RiskScorer.compute_scores()
    │       │   ├─> TestDiscovery.discover()
    │       │   │   └─> subprocess.run(["pytest", "--collect-only"])  [EXTERNAL: pytest]
    │       │   ├─> Database.get_test_history()
    │       │   ├─> TestAnalyzer.analyze_risk()
    │       │   │   ├─> PromptTemplates.risk_analysis_prompt()
    │       │   │   └─> OllamaClient.generate_json()  [EXTERNAL: LLM API call]
    │       │   └─> Returns: {test_name: risk_score}
    │       │
    │
    ├─> [PHASE 3: Test Execution]
    │   └─> TestRunner.execute_tests()
    │       ├─> Database.create_run()
    │       ├─> TestRunner._build_command()
    │       │   └─> Builds pytest-specific command with flags
    │       ├─> subprocess.run(cmd)  [EXTERNAL: pytest command]
    │       ├─> ResultParser.parse()
    │       │   ├─> ResultParser._parse_pytest_json()  [if JSON available]
    │       │   └─> ResultParser._parse_pytest_stdout() [fallback]
    │       ├─> Database.add_result() [for each test]
    │       │   └─> Database._update_test_history()
    │       └─> TestRunner._analyze_root_cause() [if failures]
    │           └─> TestAnalyzer.analyze_failure()
    │               ├─> PromptTemplates.root_cause_prompt()
    │               └─> OllamaClient.generate_json()  [EXTERNAL: LLM API call]
    │
    ├─> [PHASE 4: Report Generation]
    │   └─> ReportGenerator.generate()
    │       ├─> ReportGenerator._prepare_context()
    │       ├─> Jinja2.render(report.html)
    │       └─> Write: reports/test_report.html
    │
    └─> Exit with code (0 if pass, 1 if failures)
```

### File Structure (Current)

```
src/testrunner/
├── __init__.py              # Package metadata
├── __main__.py              # Entry point for `python -m testrunner`
├── cli.py                   # Click-based CLI (main, run, report, history commands)
├── config.py                # Pydantic config models (TestRunnerConfig, etc.)
│
├── core/
│   ├── discovery.py         # Test discovery (pytest --collect-only) [PROBLEM: pytest-specific]
│   ├── parser.py            # Result parsing (pytest JSON/stdout) [PROBLEM: pytest-specific]
│   └── runner.py            # Test orchestration (build cmd, execute, parse)
│
├── git/
│   ├── diff.py              # Git diff analysis (GitDiffAnalyzer) [GOOD: language-agnostic]
│   └── history.py           # Git history analysis (contributors, hotspots) [GOOD]
│
├── llm/
│   ├── base.py              # LLMClient abstract base class
│   ├── ollama.py            # OllamaClient implementation
│   ├── analysis.py          # TestAnalyzer (risk + root cause) [CURRENT: only for risk/root cause]
│   └── prompts.py           # Prompt templates
│
├── risk/
│   ├── scorer.py            # RiskScorer (combines LLM + historical) [PROBLEM: pre-execution]
│   └── prioritizer.py       # TestPrioritizer (sorts by risk) [PROBLEM: unnecessary]
│
├── storage/
│   ├── database.py          # SQLite operations
│   └── models.py            # Data models (TestRun, TestResult, TestHistory, etc.)
│
└── report/
    ├── generator.py         # HTML report generation (Jinja2)
    └── templates/
        ├── base.html
        └── report.html
```

### Current Problems (Why Refactoring Needed)

1. **Tight coupling to pytest**
   - `discovery.py:67-118` - Hardcoded `pytest --collect-only`
   - `parser.py:41-190` - 234 lines of pytest-specific parsing
   - `runner.py:144-162` - pytest flag injection (--json-report, -v, -x)

2. **Unnecessary pre-execution risk analysis**
   - Risk scoring happens BEFORE running tests (expensive LLM calls)
   - Test discovery required to compute risk (adds complexity)
   - Running tests is cheap - why predict?

3. **Overengineered historical tracking**
   - Complex history aggregation without clear use case
   - `test_history` table tracks failure rates, avg duration, etc.
   - Unclear value for a failure analysis tool

4. **Generic fallback is naive**
   - `parser.py:215-234` - Just regex for PASS/FAIL words
   - Doesn't actually parse test results

---

## Target Architecture (After Refactoring)

### Simplified Component Diagram

```
┌─────────────────────────────────────────────┐
│            CLI Layer (cli.py)               │
└─────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│   Git    │  │ Executor │  │ Database │
│ Analysis │  │  (run)   │  │ (store)  │
└──────────┘  └──────────┘  └──────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌─────────────────┐   ┌─────────────────┐
│   LLM Parser    │   │ Failure Analyzer│
│  (parse output) │   │ (analyze fails) │
└─────────────────┘   └─────────────────┘
        │                       │
        └───────────┬───────────┘
                    ▼
            ┌──────────────┐
            │    Report    │
            │  Generator   │
            └──────────────┘
```

### Target Execution Flow

```
User → CLI.run()
    │
    ├─> Config.load() → testrunner.json
    │
    ├─> [OPTIONAL: Git Analysis]
    │   └─> GitDiffAnalyzer.analyze()
    │       └─> Returns: {files: [...], commits: [...]}
    │
    ├─> [Execute Tests]
    │   └─> TestExecutor.execute()
    │       ├─> subprocess.run(config.test.command, shell=True)  [EXTERNAL: user's test command]
    │       └─> Returns: RawTestOutput(stdout, stderr, exit_code)
    │
    ├─> [Parse Output via LLM]
    │   └─> LLMOutputParser.parse(raw_output)
    │       ├─> Build prompt with raw stdout/stderr
    │       ├─> OllamaClient.generate_json()  [EXTERNAL: LLM API]
    │       └─> Returns: ParsedOutput(tests: [...], summary: {...})
    │
    ├─> [Store Results]
    │   └─> Database.store_run(parsed_output)
    │
    ├─> [Analyze Failures]
    │   └─> For each failed test:
    │       └─> FailureAnalyzer.analyze(test, git_changes)
    │           ├─> Build prompt with error + git context
    │           ├─> OllamaClient.generate_json()  [EXTERNAL: LLM API]
    │           └─> Returns: FailureAnalysis(cause, fix, confidence)
    │
    ├─> [Generate Report]
    │   └─> ReportGenerator.generate(results, analyses)
    │       └─> Write: reports/test_report.html
    │
    └─> Exit with code (0 if pass, 1 if failures)
```

### Target File Structure

```
src/testrunner/
├── __init__.py
├── __main__.py
├── cli.py                   # Simplified orchestration
├── config.py                # Simplified config (no pytest defaults)
│
├── core/
│   └── executor.py          # NEW: Simple subprocess.run() wrapper
│
├── git/                     # UNCHANGED
│   ├── diff.py
│   └── history.py
│
├── llm/
│   ├── base.py              # UNCHANGED
│   ├── ollama.py            # UNCHANGED
│   ├── parser.py            # NEW: LLM-based test output parser
│   ├── analyzer.py          # NEW: Failure analysis (renamed from analysis.py)
│   └── prompts.py           # UPDATED: Add parsing prompts
│
├── storage/
│   ├── database.py          # SIMPLIFIED: Remove complex history tracking
│   └── models.py            # SIMPLIFIED: Remove unused models
│
└── report/
    ├── generator.py         # UPDATED: Focus on failures
    └── templates/
        └── report.html      # UPDATED: Failure-focused layout
```

### Files to Delete

- `src/testrunner/core/discovery.py` (test discovery not needed)
- `src/testrunner/core/parser.py` (replaced by LLM parser)
- `src/testrunner/core/runner.py` (replaced by executor.py)
- `src/testrunner/risk/scorer.py` (no pre-execution risk)
- `src/testrunner/risk/prioritizer.py` (no pre-execution risk)

---

## External Dependencies & API Calls

### System Commands
1. **Git operations** (via GitPython)
   - `git diff` - Get file changes
   - `git log` - Get commit history
   - `git blame` - Attribution info

2. **Test execution** (via subprocess)
   - User-provided command (e.g., `pytest -v`, `npm test`, `go test ./...`)
   - Captures stdout, stderr, exit code

### LLM API Calls (Ollama)

**Current (3 call types):**
1. `TestAnalyzer.analyze_risk()` - Predict test failures [TO BE REMOVED]
2. `TestAnalyzer.analyze_failure()` - Root cause analysis [KEEP]
3. `TestAnalyzer.summarize_results()` - Result summary [KEEP/MAYBE]

**Target (2 call types):**
1. `LLMOutputParser.parse()` - Parse any test framework output [NEW]
2. `FailureAnalyzer.analyze()` - Root cause + suggested fix [REFACTORED]

### Database Operations

**Current Schema:**
- `test_runs` - Run metadata
- `test_results` - Individual test results
- `test_history` - Aggregated historical stats [COMPLEX]
- `risk_analysis` - Cached risk scores [TO BE REMOVED]

**Target Schema:**
- `test_runs` - Run metadata (keep)
- `test_results` - Individual test results (keep)
- Remove: `test_history`, `risk_analysis`

---

## Configuration Schema

### Current Config
```json
{
  "project": {
    "name": "my-project",
    "language": "python",
    "description": "..."
  },
  "test": {
    "command": "pytest",
    "args": ["-v", "--tb=short"],
    "test_directory": "tests/",
    "timeout_seconds": 300,
    "fail_fast": false
  },
  "llm": {...},
  "git": {...},
  "storage": {...}
}
```

### Target Config (Simplified)
```json
{
  "project": {
    "name": "my-project",
    "language": "python",  // Optional hint for LLM
    "description": "..."   // Optional context
  },
  "test": {
    "command": "pytest -v --tb=short",  // Single string, any command
    "working_directory": ".",
    "timeout_seconds": 300,
    "environment": {}  // Optional env vars
  },
  "llm": {...},  // Unchanged
  "git": {...},  // Unchanged
  "storage": {...}  // Unchanged
}
```

---

## Implementation Checkpoints

Checkpoints will be documented in `CHECKPOINT_XX.md` files as major milestones are reached:

- `CHECKPOINT_00.md` - Initial state documentation (this file)
- `CHECKPOINT_01.md` - LLM parser implementation
- `CHECKPOINT_02.md` - Failure analyzer implementation
- `CHECKPOINT_03.md` - Old code removal + integration
- `CHECKPOINT_04.md` - Multi-language validation

Each checkpoint will include:
- What was changed
- Architecture diagrams
- Sequence flows
- Design decisions
- Test results

---

## Testing Strategy

### Unit Tests
- Config loading/validation
- Database operations
- Model serialization
- LLM parser (with fixtures)

### Integration Tests
- End-to-end with fixture projects
- Python/pytest (existing)
- JavaScript/Jest (to be added)
- Go/go test (to be added)

### Fixture Projects
- `test_repos/fixture-python-calculator/` - Python with intentional divide-by-zero failure
- `test_repos/fixture-python-api/` - Flask API with intentional duplicate email validation bug
- `test_repos/fixture-javascript-calculator/` - JavaScript/Jest with intentional divide-by-zero failure

---

## Git Workflow

All changes follow this process:
1. Create feature branch (`git checkout -b feature/description`)
2. Make changes iteratively
3. Run tests (`pytest tests/`)
4. Create detailed commit messages
5. Push branch
6. Create PR with `gh pr create` (with detailed summary)
7. Merge with `gh pr merge`

**Commit Message Format:**
```
<type>: <description>

<body explaining what and why>

<any relevant context or breaking changes>
```

**IMPORTANT:** Commits must NOT include a `Co-Authored-By` line for Claude. All commits are attributed solely to the user configured in git config.

**Author:** Harshit Gupta (39994376+arelyx@users.noreply.github.com)

---

## Session Learnings

_This section captures surprising results and useful context discovered during development sessions._

### 2026-02-11: Architecture Validation & Integration Fixes

**e2e_test.py was completely broken.** The script still imported `testrunner.core.runner.TestRunner` which was removed during the architecture refactoring (commit 7a495bf). It also referenced `runner.analyze_risks()` and `runner.analyze_git_changes()` which no longer exist. The new pipeline is: `TestExecutor` → `LLMOutputParser` → `FailureAnalyzer` → `ReportGenerator`. The e2e script needed a full rewrite of `run_testrunner()` to match `cli.py:run()`.

**HINTS.md was configured but never wired up.** `config.py` had `hints_file` field and `get_hints_content()` method, but `cli.py:run()` never called it, and neither `LLMOutputParser` nor `FailureAnalyzer` accepted a hints parameter. All three fixture repos had HINTS.md files that were never being used. This is a common pattern — infrastructure gets built but the wiring gets missed.

**CLI flags are on the Click group, not subcommands.** `--config` and `--verbose` are defined on `main()` (the Click group), not on the `run` subcommand. This means the correct invocation is `testrunner --verbose run --no-report`, NOT `testrunner run --verbose`. The README had this wrong.

**Fixture repos need backdated commits.** The Python fixtures have incremental commit histories (12+ commits) where the bug is introduced in a later "simplify" commit. The JavaScript fixture initially had a single commit with everything, which doesn't give the git analysis useful context. Commits need `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` env vars set during commit.

**The `python -m testrunner run` path works but `python -m testrunner.cli run` also works.** Both are valid because `__main__.py` calls `main()` and `cli.py` has its own `if __name__ == "__main__"` guard. The README should recommend the shorter `python -m testrunner run` form.

**npm install support was missing from e2e tests.** The `install_repo_dependencies()` function only handled Python `requirements.txt` files. JavaScript fixtures need `npm install` run in the repo directory. This needs to be done before test execution.

**Fixture test counts in documentation were wrong.** The JS calculator HINTS.md and README claimed 22 tests but Jest actually reports 27 tests (4+3+5+7+5+3). Always verify test counts by running the actual test framework.

### Key Module Locations

- CLI orchestration: `src/testrunner/cli.py` (main pipeline in `run()` command)
- Test execution: `src/testrunner/core/executor.py` (simple subprocess wrapper)
- LLM parsing: `src/testrunner/llm/parser.py` (framework-agnostic output parser)
- Failure analysis: `src/testrunner/llm/analyzer.py` (root cause identification)
- Config: `src/testrunner/config.py` (Pydantic models, includes `get_hints_content()`)
- E2E tests: `scripts/e2e_test.py` + `scripts/test_repos.json`

### GitHub Fixture Repos

- `arelyx/fixture-python-calculator` - Python/pytest, divide-by-zero bug
- `arelyx/fixture-python-api` - Flask API, duplicate email validation bug
- `arelyx/fixture-javascript-calculator` - JavaScript/Jest, divide-by-zero bug

---

*End of CLAUDE.md - This file will be updated as the system evolves*
