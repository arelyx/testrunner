"""Data models for test results and history."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TestStatus(str, Enum):
    """Status of a test execution."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestRun:
    """Represents a single test run session."""

    id: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    commit_hash: Optional[str] = None
    branch: Optional[str] = None
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "commit_hash": self.commit_hash,
            "branch": self.branch,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "TestRun":
        """Create from database row."""
        return cls(
            id=row[0],
            started_at=datetime.fromisoformat(row[1]) if row[1] else None,
            finished_at=datetime.fromisoformat(row[2]) if row[2] else None,
            commit_hash=row[3],
            branch=row[4],
            total_tests=row[5] or 0,
            passed=row[6] or 0,
            failed=row[7] or 0,
            skipped=row[8] or 0,
        )


@dataclass
class TestResult:
    """Represents the result of a single test."""

    id: Optional[int] = None
    run_id: Optional[int] = None
    test_name: str = ""
    test_file: str = ""
    status: TestStatus = TestStatus.PASSED
    duration_ms: int = 0
    output: str = ""
    error_message: str = ""
    risk_score: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "test_name": self.test_name,
            "test_file": self.test_file,
            "status": self.status.value if isinstance(self.status, TestStatus) else self.status,
            "duration_ms": self.duration_ms,
            "output": self.output,
            "error_message": self.error_message,
            "risk_score": self.risk_score,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "TestResult":
        """Create from database row."""
        status_str = row[4]
        try:
            status = TestStatus(status_str)
        except ValueError:
            status = TestStatus.ERROR

        return cls(
            id=row[0],
            run_id=row[1],
            test_name=row[2],
            test_file=row[3],
            status=status,
            duration_ms=row[5] or 0,
            output=row[6] or "",
            error_message=row[7] or "",
            risk_score=row[8] if len(row) > 8 else 0.0,
        )


@dataclass
class TestHistory:
    """Historical statistics for a test."""

    test_name: str = ""
    last_failed_at: Optional[datetime] = None
    failure_count: int = 0
    total_runs: int = 0
    avg_duration_ms: float = 0.0

    @property
    def failure_rate(self) -> float:
        """Calculate the failure rate."""
        if self.total_runs == 0:
            return 0.0
        return self.failure_count / self.total_runs

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "last_failed_at": self.last_failed_at.isoformat() if self.last_failed_at else None,
            "failure_count": self.failure_count,
            "total_runs": self.total_runs,
            "failure_rate": self.failure_rate,
            "avg_duration_ms": self.avg_duration_ms,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "TestHistory":
        """Create from database row."""
        return cls(
            test_name=row[0],
            last_failed_at=datetime.fromisoformat(row[1]) if row[1] else None,
            failure_count=row[2] or 0,
            total_runs=row[3] or 0,
            avg_duration_ms=row[4] if len(row) > 4 else 0.0,
        )


@dataclass
class RiskAnalysis:
    """Risk analysis results for a test."""

    test_name: str
    risk_score: float
    risk_factors: list[str] = field(default_factory=list)
    affected_by_changes: bool = False
    historical_failure_rate: float = 0.0
    llm_confidence: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "affected_by_changes": self.affected_by_changes,
            "historical_failure_rate": self.historical_failure_rate,
            "llm_confidence": self.llm_confidence,
        }


@dataclass
class RootCauseAnalysis:
    """Root cause analysis for failing tests."""

    test_name: str
    likely_cause: str
    commit_hash: Optional[str] = None
    file_path: Optional[str] = None
    confidence: float = 0.0
    explanation: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "likely_cause": self.likely_cause,
            "commit_hash": self.commit_hash,
            "file_path": self.file_path,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "suggested_fix": self.suggested_fix,
        }
