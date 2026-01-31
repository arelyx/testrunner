"""Tests for the storage models."""

from datetime import datetime

import pytest

from testrunner.storage.models import (
    TestRun,
    TestResult,
    TestHistory,
    TestStatus,
    RiskAnalysis,
    RootCauseAnalysis,
)


class TestTestStatus:
    """Tests for TestStatus enum."""

    def test_status_values(self):
        """Test that all expected statuses exist."""
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.SKIPPED.value == "skipped"
        assert TestStatus.ERROR.value == "error"


class TestTestRun:
    """Tests for TestRun model."""

    def test_default_values(self):
        """Test default values."""
        run = TestRun()
        assert run.id is None
        assert run.total_tests == 0
        assert run.passed == 0
        assert run.failed == 0
        assert run.skipped == 0

    def test_to_dict(self):
        """Test converting to dictionary."""
        now = datetime.now()
        run = TestRun(
            id=1,
            started_at=now,
            commit_hash="abc123",
            branch="main",
            total_tests=10,
            passed=8,
            failed=2,
        )

        d = run.to_dict()
        assert d["id"] == 1
        assert d["commit_hash"] == "abc123"
        assert d["total_tests"] == 10

    def test_from_row(self):
        """Test creating from database row."""
        now = datetime.now()
        row = (
            1,  # id
            now.isoformat(),  # started_at
            now.isoformat(),  # finished_at
            "abc123",  # commit_hash
            "main",  # branch
            10,  # total_tests
            8,  # passed
            2,  # failed
            0,  # skipped
        )

        run = TestRun.from_row(row)
        assert run.id == 1
        assert run.commit_hash == "abc123"
        assert run.total_tests == 10


class TestTestResult:
    """Tests for TestResult model."""

    def test_default_values(self):
        """Test default values."""
        result = TestResult()
        assert result.status == TestStatus.PASSED
        assert result.duration_ms == 0

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = TestResult(
            id=1,
            run_id=1,
            test_name="test_example",
            test_file="tests/test_example.py",
            status=TestStatus.FAILED,
            duration_ms=100,
            error_message="Assertion failed",
        )

        d = result.to_dict()
        assert d["test_name"] == "test_example"
        assert d["status"] == "failed"
        assert d["duration_ms"] == 100


class TestTestHistory:
    """Tests for TestHistory model."""

    def test_failure_rate_no_runs(self):
        """Test failure rate with no runs."""
        history = TestHistory(test_name="test_example")
        assert history.failure_rate == 0.0

    def test_failure_rate_calculation(self):
        """Test failure rate calculation."""
        history = TestHistory(
            test_name="test_example",
            failure_count=3,
            total_runs=10,
        )
        assert history.failure_rate == 0.3

    def test_to_dict(self):
        """Test converting to dictionary."""
        history = TestHistory(
            test_name="test_example",
            failure_count=2,
            total_runs=5,
        )

        d = history.to_dict()
        assert d["test_name"] == "test_example"
        assert d["failure_rate"] == 0.4


class TestRiskAnalysis:
    """Tests for RiskAnalysis model."""

    def test_to_dict(self):
        """Test converting to dictionary."""
        analysis = RiskAnalysis(
            test_name="test_example",
            risk_score=0.8,
            risk_factors=["Recent changes", "Historical failures"],
            affected_by_changes=True,
        )

        d = analysis.to_dict()
        assert d["test_name"] == "test_example"
        assert d["risk_score"] == 0.8
        assert len(d["risk_factors"]) == 2


class TestRootCauseAnalysis:
    """Tests for RootCauseAnalysis model."""

    def test_to_dict(self):
        """Test converting to dictionary."""
        analysis = RootCauseAnalysis(
            test_name="test_example",
            likely_cause="Missing null check",
            commit_hash="abc123",
            file_path="src/module.py",
            confidence=0.85,
            suggested_fix="Add null check before accessing property",
        )

        d = analysis.to_dict()
        assert d["test_name"] == "test_example"
        assert d["confidence"] == 0.85
        assert d["commit_hash"] == "abc123"
