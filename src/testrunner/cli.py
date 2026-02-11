"""Command-line interface for TestRunner."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from testrunner import __version__
from testrunner.config import TestRunnerConfig, create_example_config, get_default_config


console = Console()


def print_banner() -> None:
    """Print the TestRunner banner."""
    console.print(
        Panel.fit(
            "[bold blue]TestRunner[/bold blue] - LLM-driven CI System",
            subtitle=f"v{__version__}",
        )
    )


@click.group()
@click.version_option(version=__version__, prog_name="testrunner")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=False),
    help="Path to configuration file (default: testrunner.json)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def main(ctx: click.Context, config: Optional[str], verbose: bool) -> None:
    """TestRunner - LLM-driven CI system for intelligent test execution.

    Predicts which tests are likely to fail, runs high-risk tests first,
    and generates detailed visual reports.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config_path"] = config


@main.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="testrunner.json",
    help="Output path for configuration file",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing configuration")
@click.pass_context
def init(ctx: click.Context, output: str, force: bool) -> None:
    """Initialize a new TestRunner configuration file."""
    print_banner()

    output_path = Path(output)
    if output_path.exists() and not force:
        console.print(
            f"[yellow]Configuration file already exists:[/yellow] {output_path}"
        )
        console.print("Use --force to overwrite")
        sys.exit(1)

    try:
        create_example_config(output_path)
        console.print(f"[green]Created configuration file:[/green] {output_path}")
        console.print("\nNext steps:")
        console.print("  1. Edit the configuration file for your project")
        console.print("  2. Create a HINTS.md file with project context (optional)")
        console.print("  3. Run [bold]testrunner run[/bold] to execute tests")
    except Exception as e:
        console.print(f"[red]Error creating configuration:[/red] {e}")
        sys.exit(1)


@main.command()
@click.option(
    "--report/--no-report",
    default=True,
    help="Generate HTML report after tests",
)
@click.pass_context
def run(ctx: click.Context, report: bool) -> None:
    """Execute tests and analyze failures."""
    print_banner()

    config_path = ctx.obj.get("config_path")
    verbose = ctx.obj.get("verbose", False)

    # Load configuration
    try:
        if config_path:
            config = TestRunnerConfig.from_file(config_path)
        else:
            config = TestRunnerConfig.find_and_load()
        console.print(f"[dim]Loaded config for project:[/dim] {config.project.name}")
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("Run [bold]testrunner init[/bold] to create a configuration file")
        sys.exit(1)

    # Import new components
    import os

    from testrunner.core.executor import TestExecutor
    from testrunner.llm.parser import LLMOutputParser
    from testrunner.llm.analyzer import FailureAnalyzer
    from testrunner.report.generator import ReportGenerator
    from testrunner.storage.models import TestStatus

    # Initialize components
    base_dir = Path(config_path).parent if config_path else Path.cwd()
    paths = config.get_absolute_paths(base_dir)

    # Ensure directories exist
    paths["report_output_dir"].mkdir(parents=True, exist_ok=True)

    # Initialize LLM client based on provider
    if config.llm.provider == "openrouter":
        from testrunner.llm.openrouter import OpenRouterClient

        api_key = None
        if config.llm.api_key_env:
            api_key = os.environ.get(config.llm.api_key_env)
        llm_client = OpenRouterClient(
            api_key=api_key,
            model=config.llm.model,
            base_url=config.llm.base_url,
            timeout=config.llm.timeout_seconds,
        )
    else:
        from testrunner.llm.ollama import OllamaClient

        llm_client = OllamaClient(
            base_url=config.llm.base_url,
            model=config.llm.model,
            timeout=config.llm.timeout_seconds,
        )

    # Initialize new components
    executor = TestExecutor(
        command=config.test.command,
        working_directory=paths["working_directory"],
        timeout_seconds=config.test.timeout_seconds,
        environment=config.test.environment,
    )
    parser = LLMOutputParser(llm_client)
    analyzer = FailureAnalyzer(llm_client)

    # Load hints file if available
    hints_content = config.get_hints_content(base_dir)
    if hints_content and verbose:
        console.print(f"[dim]Loaded hints from {config.hints_file}[/dim]")

    # Collect git changes if enabled
    git_changes = None
    if config.git.enabled:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analyzing git changes...", total=None)
            try:
                from testrunner.git.diff import GitDiffAnalyzer

                git_analyzer = GitDiffAnalyzer(base_dir)
                git_changes = git_analyzer.analyze(
                    compare_ref=config.git.compare_ref,
                    include_uncommitted=config.git.include_uncommitted,
                )
                progress.update(task, completed=True)
                if verbose and git_changes:
                    console.print(f"[dim]Found {len(git_changes.get('files', []))} changed files[/dim]")
                if git_changes and config.git.ignore_untracked:
                    git_changes.pop("untracked_files", None)
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[yellow]Warning: Git analysis failed:[/yellow] {e}")

    # Execute tests
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running tests...", total=None)
        try:
            raw_output = executor.execute()
            progress.update(task, completed=True)

            if verbose:
                console.print(f"[dim]Test execution completed in {raw_output.duration_ms}ms[/dim]")
        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"[red]Error executing tests:[/red] {e}")
            sys.exit(1)

    # Parse test output
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing test results...", total=None)
        try:
            parsed = parser.parse(
                stdout=raw_output.stdout,
                stderr=raw_output.stderr,
                exit_code=raw_output.exit_code,
                test_command=config.test.command,
                language=config.project.language,
                hints=hints_content,
            )
            progress.update(task, completed=True)

            if verbose:
                console.print(f"[dim]Parsed {len(parsed.tests)} tests (confidence: {parsed.parse_confidence:.0%})[/dim]")
                if llm_client.last_raw_content:
                    console.print("\n[bold]LLM Parser Response:[/bold]")
                    console.print(Panel(llm_client.last_raw_content, border_style="dim", expand=False))
        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"[red]Error parsing test output:[/red] {e}")
            sys.exit(1)

    # Display results summary
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
    _display_results_summary(results_dict)

    # Analyze failures
    failure_analyses = []
    if parsed.failed > 0:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Analyzing {parsed.failed} failures...", total=None)
            try:
                failed_tests = [t for t in parsed.tests if t.status == TestStatus.FAILED]
                failure_analyses = analyzer.analyze_multiple(failed_tests, git_changes, hints_content)
                progress.update(task, completed=True)

                if verbose:
                    console.print(f"[dim]Generated {len(failure_analyses)} failure analyses[/dim]")
                    # Show LLM responses for each analysis
                    # The parser used 1 call; remaining log entries are from the analyzer
                    analyzer_responses = llm_client.response_log[1:]  # Skip parser response
                    for i, resp in enumerate(analyzer_responses):
                        label = failure_analyses[i].test_name if i < len(failure_analyses) else f"Analysis {i+1}"
                        console.print(f"\n[bold]LLM Analysis — {label}:[/bold]")
                        console.print(Panel(resp, border_style="dim", expand=False))
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[yellow]Warning: Failure analysis failed:[/yellow] {e}")

    # Generate report
    if report:
        console.print("\n[bold]Generating report...[/bold]")
        try:
            report_gen = ReportGenerator(config, base_dir)
            analysis_data = {
                "git_changes": git_changes,
                "failure_analyses": [a.to_dict() for a in failure_analyses],
            }
            report_path = report_gen.generate(results_dict, analysis_data)
            console.print(f"[green]Report generated:[/green] {report_path}")
        except Exception as e:
            console.print(f"[red]Error generating report:[/red] {e}")

    # Exit with appropriate code
    if parsed.failed > 0:
        sys.exit(1)


def _display_results_summary(results: dict) -> None:
    """Display a summary of test results."""
    total = results.get("total", 0)
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    skipped = results.get("skipped", 0)

    console.print("\n" + "=" * 50)
    console.print("[bold]Test Results Summary[/bold]")
    console.print("=" * 50)

    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Tests", str(total))
    table.add_row("Passed", f"[green]{passed}[/green]")
    table.add_row("Failed", f"[red]{failed}[/red]")
    table.add_row("Skipped", f"[yellow]{skipped}[/yellow]")

    if total > 0:
        pass_rate = (passed / total) * 100
        table.add_row("Pass Rate", f"{pass_rate:.1f}%")

    console.print(table)

    if failed > 0:
        console.print("\n[red]Some tests failed![/red]")
        if results.get("failed_tests"):
            console.print("\nFailed tests:")
            for test in results["failed_tests"][:10]:  # Show first 10
                console.print(f"  [red]✗[/red] {test.get('name', 'Unknown')}")
            if len(results["failed_tests"]) > 10:
                console.print(f"  ... and {len(results['failed_tests']) - 10} more")
    else:
        console.print("\n[green]All tests passed![/green]")


if __name__ == "__main__":
    main()
