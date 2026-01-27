"""Risk scoring for tests based on multiple factors."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from testrunner.config import TestRunnerConfig
from testrunner.storage.database import Database
from testrunner.storage.models import RiskAnalysis


@dataclass
class RiskFactors:
    """Breakdown of risk factors for a test."""

    historical_failure_rate: float = 0.0
    recently_failed: bool = False
    affected_by_changes: bool = False
    llm_risk_score: float = 0.0
    file_change_proximity: float = 0.0

    def compute_total_score(self, weights: Optional[dict[str, float]] = None) -> float:
        """Compute weighted total risk score.

        Args:
            weights: Optional custom weights for each factor

        Returns:
            Total risk score between 0.0 and 1.0
        """
        default_weights = {
            "historical_failure_rate": 0.25,
            "recently_failed": 0.20,
            "affected_by_changes": 0.15,
            "llm_risk_score": 0.25,
            "file_change_proximity": 0.15,
        }
        weights = weights or default_weights

        score = 0.0
        score += self.historical_failure_rate * weights.get("historical_failure_rate", 0.25)
        score += (1.0 if self.recently_failed else 0.0) * weights.get("recently_failed", 0.20)
        score += (1.0 if self.affected_by_changes else 0.0) * weights.get("affected_by_changes", 0.15)
        score += self.llm_risk_score * weights.get("llm_risk_score", 0.25)
        score += self.file_change_proximity * weights.get("file_change_proximity", 0.15)

        return min(1.0, max(0.0, score))


class RiskScorer:
    """Computes risk scores for tests combining multiple signals."""

    def __init__(
        self,
        config: TestRunnerConfig,
        database: Database,
        base_dir: Path,
    ):
        """Initialize the risk scorer.

        Args:
            config: TestRunner configuration
            database: Database for historical data
            base_dir: Base directory of the project
        """
        self.config = config
        self.db = database
        self.base_dir = base_dir

    def compute_scores(
        self,
        git_changes: Optional[dict[str, Any]] = None,
        hints: Optional[str] = None,
    ) -> dict[str, float]:
        """Compute risk scores for all discovered tests.

        Args:
            git_changes: Optional git change analysis
            hints: Optional hints file content

        Returns:
            Dictionary mapping test names to risk scores
        """
        from testrunner.core.discovery import TestDiscovery

        # Discover tests
        discovery = TestDiscovery(self.config, self.base_dir)
        discovered = discovery.discover()

        if not discovered.success:
            return {}

        test_names = [t.name for t in discovered.tests]
        test_files = [t.file_path for t in discovered.tests]

        # Get historical failure data
        historical_data = self._get_historical_data(test_names)

        # Get LLM risk analysis
        llm_risks = self._get_llm_risks(
            git_changes=git_changes,
            test_files=test_files,
            hints=hints,
            historical_data=historical_data,
        )

        # Compute file proximity scores
        proximity_scores = self._compute_proximity_scores(
            test_files=test_files,
            changed_files=git_changes.get("files", []) if git_changes else [],
        )

        # Combine all factors into final scores
        scores = {}
        for test in discovered.tests:
            factors = RiskFactors(
                historical_failure_rate=historical_data.get(test.name, {}).get(
                    "failure_rate", 0.0
                ),
                recently_failed=historical_data.get(test.name, {}).get(
                    "recently_failed", False
                ),
                affected_by_changes=test.file_path in proximity_scores
                and proximity_scores[test.file_path] > 0,
                llm_risk_score=llm_risks.get(test.name, 0.0),
                file_change_proximity=proximity_scores.get(test.file_path, 0.0),
            )

            scores[test.name] = factors.compute_total_score()

        return scores

    def _get_historical_data(self, test_names: list[str]) -> dict[str, dict]:
        """Get historical failure data for tests.

        Args:
            test_names: List of test names

        Returns:
            Dictionary mapping test names to historical data
        """
        data = {}

        for name in test_names:
            history = self.db.get_test_history(name)
            if history:
                data[name] = {
                    "failure_rate": history.failure_rate,
                    "recently_failed": history.last_failed_at is not None,
                    "total_runs": history.total_runs,
                }

        # Also get recently failed tests
        recent_failures = self.db.get_recently_failed_tests(days=7)
        for history in recent_failures:
            if history.test_name in data:
                data[history.test_name]["recently_failed"] = True
            else:
                data[history.test_name] = {
                    "failure_rate": history.failure_rate,
                    "recently_failed": True,
                    "total_runs": history.total_runs,
                }

        return data

    def _get_llm_risks(
        self,
        git_changes: Optional[dict[str, Any]],
        test_files: list[str],
        hints: Optional[str],
        historical_data: dict[str, dict],
    ) -> dict[str, float]:
        """Get risk scores from LLM analysis.

        Args:
            git_changes: Git change analysis
            test_files: List of test files
            hints: Hints file content
            historical_data: Historical failure data

        Returns:
            Dictionary mapping test names to LLM risk scores
        """
        if not git_changes or not git_changes.get("files"):
            return {}

        try:
            from testrunner.llm.analysis import TestAnalyzer

            analyzer = TestAnalyzer(self.config, self.base_dir)

            # Format historical failures for the prompt
            historical_failures = [
                {"test_name": name, "failure_rate": data.get("failure_rate", 0)}
                for name, data in historical_data.items()
                if data.get("failure_rate", 0) > 0.1
            ]

            analyses = analyzer.analyze_risk(
                changed_files=git_changes.get("files", []),
                test_files=test_files,
                hints=hints,
                historical_failures=historical_failures,
            )

            return {a.test_name: a.llm_confidence for a in analyses}

        except Exception:
            return {}

    def _compute_proximity_scores(
        self,
        test_files: list[str],
        changed_files: list[dict],
    ) -> dict[str, float]:
        """Compute proximity scores based on file relationships.

        Tests get higher scores if they're in directories close to changed files.

        Args:
            test_files: List of test file paths
            changed_files: List of changed file info dicts

        Returns:
            Dictionary mapping test files to proximity scores
        """
        scores = {}

        if not changed_files:
            return scores

        changed_paths = [Path(f.get("path", "")) for f in changed_files]

        for test_file in test_files:
            test_path = Path(test_file)
            max_proximity = 0.0

            for changed_path in changed_paths:
                proximity = self._calculate_path_proximity(test_path, changed_path)
                max_proximity = max(max_proximity, proximity)

            scores[test_file] = max_proximity

        return scores

    def _calculate_path_proximity(self, path1: Path, path2: Path) -> float:
        """Calculate proximity score between two paths.

        Higher score means paths are more closely related.

        Args:
            path1: First path
            path2: Second path

        Returns:
            Proximity score between 0.0 and 1.0
        """
        # Same file
        if path1 == path2:
            return 1.0

        # Get parent directories
        parts1 = path1.parts
        parts2 = path2.parts

        # Count common prefix
        common = 0
        for p1, p2 in zip(parts1, parts2):
            if p1 == p2:
                common += 1
            else:
                break

        # Calculate proximity based on shared path depth
        max_depth = max(len(parts1), len(parts2))
        if max_depth == 0:
            return 0.0

        # Score based on shared prefix ratio
        return common / max_depth
