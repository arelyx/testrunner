#!/usr/bin/env python3
"""End-to-end test script for TestRunner.

This script:
1. Creates the test_repos directory if it doesn't exist
2. Clones/pulls test fixture repositories from GitHub
3. Runs testrunner on each repository using the new architecture
4. Displays results and verifies expected behavior
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for testrunner imports
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def load_config() -> dict:
    """Load test repos configuration."""
    config_path = SCRIPT_DIR / "test_repos.json"
    if not config_path.exists():
        console.print(f"[red]Error: Config file not found: {config_path}[/red]")
        sys.exit(1)

    with open(config_path) as f:
        return json.load(f)


def ensure_test_repos_dir(config: dict) -> Path:
    """Create test_repos directory if it doesn't exist."""
    test_repos_dir = PROJECT_ROOT / config.get("test_repos_dir", "test_repos")
    test_repos_dir.mkdir(parents=True, exist_ok=True)
    return test_repos_dir


def clone_or_pull_repo(repo: dict, test_repos_dir: Path) -> bool:
    """Clone a repo if it doesn't exist, or pull if it does.

    Returns True if successful, False otherwise.
    """
    repo_name = repo["name"]
    repo_url = repo["url"]
    repo_path = test_repos_dir / repo_name

    try:
        if repo_path.exists() and (repo_path / ".git").exists():
            # Repo exists, pull latest
            console.print(f"  [dim]Pulling latest for {repo_name}...[/dim]")
            result = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                console.print(f"  [yellow]Warning: Pull failed, using existing state[/yellow]")
            return True
        else:
            # Clone repo
            console.print(f"  [dim]Cloning {repo_name}...[/dim]")
            if repo_path.exists():
                import shutil
                shutil.rmtree(repo_path)

            result = subprocess.run(
                ["git", "clone", repo_url, str(repo_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                console.print(f"  [red]Error cloning: {result.stderr}[/red]")
                return False
            return True

    except subprocess.TimeoutExpired:
        console.print(f"  [red]Timeout while cloning/pulling {repo_name}[/red]")
        return False
    except Exception as e:
        console.print(f"  [red]Error: {e}[/red]")
        return False


def install_repo_dependencies(repo_path: Path) -> bool:
    """Install dependencies for a test repository.

    Handles both Python (requirements.txt) and Node.js (package.json) projects.
    """
    # Python dependencies
    requirements_file = repo_path / "requirements.txt"
    if requirements_file.exists():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements_file), "-q"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                console.print(f"  [yellow]Warning: pip install failed[/yellow]")
                return False
        except Exception:
            return False

    # Node.js dependencies
    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            console.print(f"  [dim]Installing npm dependencies...[/dim]")
            result = subprocess.run(
                ["npm", "install"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                console.print(f"  [yellow]Warning: npm install failed[/yellow]")
                return False
        except Exception:
            return False

    return True


def run_testrunner(repo_path: Path, config: dict) -> dict:
    """Run testrunner on a repository using the new architecture.

    Uses: TestExecutor -> LLMOutputParser -> FailureAnalyzer -> ReportGenerator

    Returns a dict with:
    - success: bool
    - total: int
    - passed: int
    - failed: int
    - skipped: int
    - failed_tests: list[str]
    - failure_analyses: list[dict]
    - report_path: Optional[str]
    - error: Optional[str]
    """
    try:
        # Import testrunner components (new architecture)
        from testrunner.config import TestRunnerConfig
        from testrunner.core.executor import TestExecutor
        from testrunner.llm.parser import LLMOutputParser
        from testrunner.llm.analyzer import FailureAnalyzer
        from testrunner.llm.ollama import OllamaClient
        from testrunner.storage.models import TestStatus
        from testrunner.report.generator import ReportGenerator

        # Load repo's testrunner config
        config_file = repo_path / "testrunner.json"
        if not config_file.exists():
            return {"success": False, "error": "No testrunner.json found"}

        tr_config = TestRunnerConfig.from_file(config_file)

        # Override LLM settings from e2e config
        if "ollama" in config:
            tr_config.llm.base_url = config["ollama"]["base_url"]
            tr_config.llm.model = config["ollama"]["model"]

        # Setup paths
        paths = tr_config.get_absolute_paths(repo_path)
        paths["report_output_dir"].mkdir(parents=True, exist_ok=True)

        # Initialize components
        llm_client = OllamaClient(
            base_url=tr_config.llm.base_url,
            model=tr_config.llm.model,
            timeout=tr_config.llm.timeout_seconds,
        )

        executor = TestExecutor(
            command=tr_config.test.command,
            working_directory=paths["working_directory"],
            timeout_seconds=tr_config.test.timeout_seconds,
            environment=tr_config.test.environment,
        )
        parser = LLMOutputParser(llm_client)
        analyzer = FailureAnalyzer(llm_client)

        # Load hints file if available
        hints_content = tr_config.get_hints_content(repo_path)

        # Collect git changes
        git_changes = None
        if tr_config.git.enabled:
            try:
                from testrunner.git.diff import GitDiffAnalyzer
                git_analyzer = GitDiffAnalyzer(repo_path)
                git_changes = git_analyzer.analyze(
                    compare_ref=tr_config.git.compare_ref,
                    include_uncommitted=tr_config.git.include_uncommitted,
                )
            except Exception:
                pass

        # Execute tests
        raw_output = executor.execute()

        # Parse output via LLM
        parsed = parser.parse(
            stdout=raw_output.stdout,
            stderr=raw_output.stderr,
            exit_code=raw_output.exit_code,
            test_command=tr_config.test.command,
            language=tr_config.project.language,
            hints=hints_content,
        )

        # Build results dict
        results_dict = {
            "total": parsed.total,
            "passed": parsed.passed,
            "failed": parsed.failed,
            "skipped": parsed.skipped,
            "duration_ms": parsed.duration_ms,
            "results": [t.to_dict() for t in parsed.tests],
            "failed_tests": [t.to_dict() for t in parsed.tests if t.status == TestStatus.FAILED],
            "raw_output": parsed.raw_output,
        }

        # Analyze failures
        failure_analyses = []
        if parsed.failed > 0:
            try:
                failed_tests = [t for t in parsed.tests if t.status == TestStatus.FAILED]
                failure_analyses = analyzer.analyze_multiple(failed_tests, git_changes, hints_content)
            except Exception:
                pass

        # Generate report
        report_path = None
        try:
            report_gen = ReportGenerator(tr_config, repo_path)
            analysis_data = {
                "git_changes": git_changes,
                "failure_analyses": [a.to_dict() for a in failure_analyses],
            }
            report_path = str(report_gen.generate(results_dict, analysis_data))
        except Exception:
            pass

        return {
            "success": True,
            "total": parsed.total,
            "passed": parsed.passed,
            "failed": parsed.failed,
            "skipped": parsed.skipped,
            "failed_tests": [t.test_name for t in parsed.tests if t.status == TestStatus.FAILED],
            "failure_analyses": [a.to_dict() for a in failure_analyses],
            "report_path": report_path,
        }

    except Exception as e:
        import traceback
        return {"success": False, "error": f"{str(e)}\n{traceback.format_exc()}"}


def display_results(all_results: list[dict]) -> None:
    """Display a summary of all test results."""
    console.print()
    console.print(Panel.fit("[bold]E2E Test Results Summary[/bold]"))

    # Results table
    table = Table(title="Repository Test Results")
    table.add_column("Repository", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Passed", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Expected Failures", justify="right")
    table.add_column("Status", justify="center")

    all_passed = True

    for result in all_results:
        repo_name = result["repo_name"]
        expected_failures = result.get("expected_failures", 0)

        if result.get("success"):
            total = result.get("total", 0)
            passed = result.get("passed", 0)
            failed = result.get("failed", 0)

            # Check if failures match expected
            if failed == expected_failures:
                status = "[green]PASS[/green]"
            else:
                status = f"[red]FAIL (expected {expected_failures} failures)[/red]"
                all_passed = False

            table.add_row(
                repo_name,
                str(total),
                str(passed),
                str(failed),
                str(expected_failures),
                status,
            )
        else:
            table.add_row(
                repo_name,
                "-",
                "-",
                "-",
                str(expected_failures),
                f"[red]ERROR: {result.get('error', 'Unknown')[:80]}[/red]",
            )
            all_passed = False

    console.print(table)

    # Show failed tests
    console.print()
    for result in all_results:
        if result.get("success") and result.get("failed_tests"):
            console.print(f"[bold]{result['repo_name']}[/bold] failed tests:")
            for test in result["failed_tests"]:
                console.print(f"  [red]\u2717[/red] {test}")

    # Show failure analyses
    console.print()
    console.print("[bold]Failure Analyses:[/bold]")
    for result in all_results:
        if result.get("success") and result.get("failure_analyses"):
            console.print(f"\n[cyan]{result['repo_name']}[/cyan]:")

            for analysis in result["failure_analyses"]:
                console.print(f"  Test: {analysis.get('test_name', 'unknown')}")
                console.print(f"  Cause: {analysis.get('likely_cause', 'unknown')}")
                suspected = analysis.get('suspected_file', 'unknown')
                confidence = analysis.get('confidence', 0)
                console.print(f"  Suspected file: {suspected} (confidence: {confidence:.0%})")
                console.print(f"  Fix: {analysis.get('suggested_fix', 'N/A')[:100]}")
                console.print()

    # Show report locations
    console.print()
    console.print("[bold]Generated Reports:[/bold]")
    for result in all_results:
        if result.get("report_path"):
            console.print(f"  {result['repo_name']}: {result['report_path']}")

    # Final status
    console.print()
    if all_passed:
        console.print("[bold green]All E2E tests passed![/bold green]")
    else:
        console.print("[bold red]Some E2E tests failed![/bold red]")
        sys.exit(1)


def main():
    """Main entry point."""
    console.print(Panel.fit(
        "[bold blue]TestRunner E2E Test Suite[/bold blue]",
        subtitle="Testing fixture repositories",
    ))

    # Load configuration
    config = load_config()
    console.print(f"[dim]Loaded config with {len(config['repos'])} test repos[/dim]")

    # Ensure test_repos directory exists
    test_repos_dir = ensure_test_repos_dir(config)
    console.print(f"[dim]Test repos directory: {test_repos_dir}[/dim]")

    # Clone/pull repositories
    console.print("\n[bold]Step 1: Preparing test repositories[/bold]")
    for repo in config["repos"]:
        console.print(f"  {repo['name']}")
        if not clone_or_pull_repo(repo, test_repos_dir):
            console.print(f"[red]Failed to prepare {repo['name']}, skipping...[/red]")
            continue

        # Install dependencies
        repo_path = test_repos_dir / repo["name"]
        install_repo_dependencies(repo_path)

    # Run testrunner on each repository
    console.print("\n[bold]Step 2: Running TestRunner on each repository[/bold]")
    all_results = []

    for repo in config["repos"]:
        repo_name = repo["name"]
        repo_path = test_repos_dir / repo_name

        if not repo_path.exists():
            all_results.append({
                "repo_name": repo_name,
                "success": False,
                "error": "Repository not found",
                "expected_failures": repo.get("expected_failures", 0),
            })
            continue

        console.print(f"\n  [cyan]{repo_name}[/cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Running tests with LLM analysis...", total=None)
            result = run_testrunner(repo_path, config)
            progress.update(task, completed=True)

        result["repo_name"] = repo_name
        result["expected_failures"] = repo.get("expected_failures", 0)
        all_results.append(result)

        if result.get("success"):
            console.print(f"    Total: {result['total']}, Passed: {result['passed']}, Failed: {result['failed']}")
        else:
            console.print(f"    [red]Error: {result.get('error', 'Unknown')[:200]}[/red]")

    # Display summary
    display_results(all_results)


if __name__ == "__main__":
    main()
