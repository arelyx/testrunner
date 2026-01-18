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
    "--priority-only",
    is_flag=True,
    help="Only run high-priority tests",
)
@click.option(
    "--skip-llm",
    is_flag=True,
    help="Skip LLM analysis (use historical data only)",
)
@click.option(
    "--report/--no-report",
    default=True,
    help="Generate HTML report after tests",
)
@click.pass_context
def run(ctx: click.Context, priority_only: bool, skip_llm: bool, report: bool) -> None:
    """Execute tests with intelligent prioritization."""
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

    # Import here to avoid circular imports and allow lazy loading
    from testrunner.core.runner import TestRunner
    from testrunner.storage.database import Database
    from testrunner.report.generator import ReportGenerator

    # Initialize components
    base_dir = Path(config_path).parent if config_path else Path.cwd()
    paths = config.get_absolute_paths(base_dir)

    # Ensure directories exist
    paths["report_output_dir"].mkdir(parents=True, exist_ok=True)
    paths["database_path"].parent.mkdir(parents=True, exist_ok=True)

    # Initialize database
    db = Database(paths["database_path"])

    # Run tests
    runner = TestRunner(config, db, base_dir, verbose=verbose)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Phase 1: Git analysis (if enabled)
        if config.git.enabled:
            task = progress.add_task("Analyzing git changes...", total=None)
            try:
                changes = runner.analyze_git_changes()
                progress.update(task, completed=True)
                if verbose and changes:
                    console.print(f"[dim]Found {len(changes.get('files', []))} changed files[/dim]")
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[yellow]Warning: Git analysis failed:[/yellow] {e}")

        # Phase 2: LLM risk analysis (if not skipped)
        if not skip_llm:
            task = progress.add_task("Analyzing test risks with LLM...", total=None)
            try:
                runner.analyze_risks()
                progress.update(task, completed=True)
            except Exception as e:
                progress.update(task, completed=True)
                console.print(f"[yellow]Warning: LLM analysis failed:[/yellow] {e}")
                console.print("[dim]Continuing with historical data only[/dim]")

        # Phase 3: Execute tests
        task = progress.add_task("Running tests...", total=None)
        try:
            results = runner.execute_tests(priority_only=priority_only)
            progress.update(task, completed=True)
        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"[red]Error running tests:[/red] {e}")
            sys.exit(1)

    # Display results summary
    _display_results_summary(results)

    # Generate report
    if report:
        console.print("\n[bold]Generating report...[/bold]")
        try:
            report_gen = ReportGenerator(config, base_dir)
            report_path = report_gen.generate(results, runner.get_analysis_data())
            console.print(f"[green]Report generated:[/green] {report_path}")
        except Exception as e:
            console.print(f"[red]Error generating report:[/red] {e}")

    # Exit with appropriate code
    if results.get("failed", 0) > 0:
        sys.exit(1)


@main.command()
@click.option(
    "--run-id",
    type=int,
    help="Generate report for a specific run ID (default: latest)",
)
@click.pass_context
def report(ctx: click.Context, run_id: Optional[int]) -> None:
    """Generate or regenerate a test report."""
    print_banner()

    config_path = ctx.obj.get("config_path")

    # Load configuration
    try:
        if config_path:
            config = TestRunnerConfig.from_file(config_path)
        else:
            config = TestRunnerConfig.find_and_load()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    from testrunner.storage.database import Database
    from testrunner.report.generator import ReportGenerator

    base_dir = Path(config_path).parent if config_path else Path.cwd()
    paths = config.get_absolute_paths(base_dir)

    # Initialize database
    db = Database(paths["database_path"])

    # Get results
    if run_id:
        results = db.get_run_results(run_id)
    else:
        results = db.get_latest_run_results()

    if not results:
        console.print("[yellow]No test results found[/yellow]")
        console.print("Run [bold]testrunner run[/bold] first to execute tests")
        sys.exit(1)

    # Generate report
    try:
        report_gen = ReportGenerator(config, base_dir)
        report_path = report_gen.generate(results)
        console.print(f"[green]Report generated:[/green] {report_path}")
    except Exception as e:
        console.print(f"[red]Error generating report:[/red] {e}")
        sys.exit(1)


@main.command()
@click.option("--limit", "-n", type=int, default=10, help="Number of runs to show")
@click.pass_context
def history(ctx: click.Context, limit: int) -> None:
    """Show test run history."""
    print_banner()

    config_path = ctx.obj.get("config_path")

    try:
        if config_path:
            config = TestRunnerConfig.from_file(config_path)
        else:
            config = TestRunnerConfig.find_and_load()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    from testrunner.storage.database import Database

    base_dir = Path(config_path).parent if config_path else Path.cwd()
    paths = config.get_absolute_paths(base_dir)

    db = Database(paths["database_path"])
    runs = db.get_recent_runs(limit)

    if not runs:
        console.print("[yellow]No test runs found[/yellow]")
        return

    table = Table(title="Test Run History")
    table.add_column("ID", style="cyan")
    table.add_column("Date", style="dim")
    table.add_column("Branch")
    table.add_column("Commit", style="dim")
    table.add_column("Total", justify="right")
    table.add_column("Passed", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Skipped", justify="right", style="yellow")

    for run in runs:
        table.add_row(
            str(run.id),
            run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "-",
            run.branch or "-",
            run.commit_hash[:8] if run.commit_hash else "-",
            str(run.total_tests),
            str(run.passed),
            str(run.failed),
            str(run.skipped),
        )

    console.print(table)


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
