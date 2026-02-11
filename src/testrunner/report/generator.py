"""Report generation using Jinja2 templates."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from testrunner.config import TestRunnerConfig


class ReportGenerator:
    """Generates static HTML reports from test results."""

    def __init__(self, config: TestRunnerConfig, base_dir: Path):
        """Initialize the report generator.

        Args:
            config: TestRunner configuration
            base_dir: Base directory of the project
        """
        self.config = config
        self.base_dir = base_dir

        # Set up Jinja2 environment
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Add custom filters
        self.env.filters["duration_format"] = self._format_duration
        self.env.filters["datetime_format"] = self._format_datetime
        self.env.filters["percentage"] = self._format_percentage

    def generate(
        self,
        results: dict[str, Any],
        analysis_data: Optional[dict[str, Any]] = None,
    ) -> Path:
        """Generate an HTML report.

        Args:
            results: Test results dictionary
            analysis_data: Optional analysis data (git changes, risk scores, etc.)

        Returns:
            Path to the generated report file
        """
        analysis_data = analysis_data or {}

        # Prepare template context
        context = self._prepare_context(results, analysis_data)

        # Render template
        template = self.env.get_template("report.html")
        html_content = template.render(**context)

        # Write report file
        output_dir = self.base_dir / self.config.report.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / self.config.report.filename
        report_path.write_text(html_content, encoding="utf-8")

        return report_path

    def _prepare_context(
        self,
        results: dict[str, Any],
        analysis_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare context for template rendering.

        Args:
            results: Test results
            analysis_data: Analysis data

        Returns:
            Template context dictionary
        """
        # Calculate statistics
        total = results.get("total", 0)
        passed = results.get("passed", 0)
        failed = results.get("failed", 0)
        skipped = results.get("skipped", 0)

        pass_rate = (passed / total * 100) if total > 0 else 0

        # Get run info
        run_info = results.get("run", {})

        # Organize test results by status
        all_results = results.get("results", [])
        failed_tests = [r for r in all_results if r.get("status") == "failed"]
        passed_tests = [r for r in all_results if r.get("status") == "passed"]
        skipped_tests = [r for r in all_results if r.get("status") == "skipped"]

        # Sort by duration (slowest first) for performance insights
        for tests in [failed_tests, passed_tests, skipped_tests]:
            tests.sort(key=lambda t: t.get("duration_ms", 0), reverse=True)

        # Prepare git changes
        git_changes = analysis_data.get("git_changes", {})
        changed_files = git_changes.get("files", [])
        untracked_files = git_changes.get("untracked_files", [])
        recent_commits = git_changes.get("commits", [])

        # Prepare failure analysis (LLM-generated root cause analysis)
        failure_analyses = analysis_data.get("failure_analyses", [])

        return {
            "title": self.config.report.title,
            "project_name": self.config.project.name,
            "generated_at": datetime.now(),
            "run_info": run_info,
            # Statistics
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": pass_rate,
            "duration_ms": results.get("duration_ms", 0),
            # Test results
            "failed_tests": failed_tests,
            "passed_tests": passed_tests,
            "skipped_tests": skipped_tests,
            "all_results": all_results,
            # Analysis (LLM-powered failure analysis)
            "failure_analyses": failure_analyses,
            "changed_files": changed_files[:20],  # Limit for display
            "untracked_files": untracked_files[:20],
            "recent_commits": recent_commits[:10],
            # Raw output
            "raw_output": results.get("raw_output", ""),
        }

    @staticmethod
    def _format_duration(ms: int) -> str:
        """Format duration in milliseconds to human-readable string."""
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms / 1000:.2f}s"
        else:
            minutes = ms // 60000
            seconds = (ms % 60000) / 1000
            return f"{minutes}m {seconds:.1f}s"

    @staticmethod
    def _format_datetime(dt: Any) -> str:
        """Format datetime object or string."""
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                return dt

        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        return str(dt)

    @staticmethod
    def _format_percentage(value: float) -> str:
        """Format a decimal as percentage."""
        return f"{value:.1f}%"
