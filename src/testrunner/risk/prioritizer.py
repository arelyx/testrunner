"""Test prioritization based on risk scores."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PrioritizedTest:
    """A test with its priority information."""

    name: str
    file_path: str
    risk_score: float
    priority_rank: int
    risk_category: str  # 'high', 'medium', 'low'

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "risk_score": self.risk_score,
            "priority_rank": self.priority_rank,
            "risk_category": self.risk_category,
        }


class TestPrioritizer:
    """Prioritizes tests based on risk scores."""

    # Risk thresholds
    HIGH_RISK_THRESHOLD = 0.6
    MEDIUM_RISK_THRESHOLD = 0.3

    def __init__(
        self,
        high_threshold: Optional[float] = None,
        medium_threshold: Optional[float] = None,
    ):
        """Initialize the prioritizer.

        Args:
            high_threshold: Threshold for high risk (default: 0.6)
            medium_threshold: Threshold for medium risk (default: 0.3)
        """
        self.high_threshold = high_threshold or self.HIGH_RISK_THRESHOLD
        self.medium_threshold = medium_threshold or self.MEDIUM_RISK_THRESHOLD

    def prioritize(
        self,
        tests: list[dict],
        risk_scores: dict[str, float],
    ) -> list[PrioritizedTest]:
        """Prioritize tests based on risk scores.

        Args:
            tests: List of test info dicts with 'name' and 'file_path'
            risk_scores: Dictionary mapping test names to risk scores

        Returns:
            List of PrioritizedTest sorted by priority (highest first)
        """
        prioritized = []

        for test in tests:
            name = test.get("name", "")
            file_path = test.get("file_path", "")
            score = risk_scores.get(name, 0.0)

            category = self._categorize_risk(score)

            prioritized.append(
                PrioritizedTest(
                    name=name,
                    file_path=file_path,
                    risk_score=score,
                    priority_rank=0,  # Will be set after sorting
                    risk_category=category,
                )
            )

        # Sort by risk score (highest first)
        prioritized.sort(key=lambda t: t.risk_score, reverse=True)

        # Assign ranks
        for i, test in enumerate(prioritized):
            test.priority_rank = i + 1

        return prioritized

    def _categorize_risk(self, score: float) -> str:
        """Categorize risk score into high/medium/low.

        Args:
            score: Risk score between 0.0 and 1.0

        Returns:
            Risk category string
        """
        if score >= self.high_threshold:
            return "high"
        elif score >= self.medium_threshold:
            return "medium"
        else:
            return "low"

    def get_high_risk_tests(
        self,
        prioritized: list[PrioritizedTest],
    ) -> list[PrioritizedTest]:
        """Get only high-risk tests.

        Args:
            prioritized: List of prioritized tests

        Returns:
            List of high-risk tests
        """
        return [t for t in prioritized if t.risk_category == "high"]

    def get_tests_by_category(
        self,
        prioritized: list[PrioritizedTest],
    ) -> dict[str, list[PrioritizedTest]]:
        """Group tests by risk category.

        Args:
            prioritized: List of prioritized tests

        Returns:
            Dictionary mapping categories to tests
        """
        return {
            "high": [t for t in prioritized if t.risk_category == "high"],
            "medium": [t for t in prioritized if t.risk_category == "medium"],
            "low": [t for t in prioritized if t.risk_category == "low"],
        }

    def get_execution_order(
        self,
        prioritized: list[PrioritizedTest],
        max_tests: Optional[int] = None,
    ) -> list[str]:
        """Get test names in execution order.

        Args:
            prioritized: List of prioritized tests
            max_tests: Optional maximum number of tests to return

        Returns:
            List of test names in execution order
        """
        names = [t.name for t in prioritized]

        if max_tests:
            return names[:max_tests]

        return names
