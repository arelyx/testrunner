"""Tests for the database module."""

import tempfile
from pathlib import Path

import pytest

from testrunner.storage.database import Database
from testrunner.storage.models import TestResult, TestStatus


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        yield database


class TestDatabase:
    """Tests for the Database class."""

    def test_create_run(self, db):
        """Test creating a test run."""
        run = db.create_run(commit_hash="abc123", branch="main")

        assert run.id is not None
        assert run.commit_hash == "abc123"
        assert run.branch == "main"
        assert run.started_at is not None

    def test_finish_run(self, db):
        """Test finishing a test run."""
        run = db.create_run()
        run.total_tests = 10
        run.passed = 8
        run.failed = 2

        db.finish_run(run)

        # Retrieve and verify
        retrieved = db.get_run(run.id)
        assert retrieved.total_tests == 10
        assert retrieved.passed == 8
        assert retrieved.failed == 2
        assert retrieved.finished_at is not None

    def test_add_result(self, db):
        """Test adding a test result."""
        run = db.create_run()

        result = TestResult(
            run_id=run.id,
            test_name="test_example",
            test_file="tests/test_example.py",
            status=TestStatus.PASSED,
            duration_ms=100,
        )

        saved = db.add_result(result)
        assert saved.id is not None

    def test_get_run_results(self, db):
        """Test getting all results for a run."""
        run = db.create_run()
        run.total_tests = 2
        run.passed = 1
        run.failed = 1

        db.add_result(TestResult(
            run_id=run.id,
            test_name="test_pass",
            status=TestStatus.PASSED,
        ))

        db.add_result(TestResult(
            run_id=run.id,
            test_name="test_fail",
            status=TestStatus.FAILED,
            error_message="Assertion error",
        ))

        db.finish_run(run)

        results = db.get_run_results(run.id)
        assert results["total"] == 2
        assert results["passed"] == 1
        assert results["failed"] == 1
        assert len(results["results"]) == 2

    def test_get_latest_run_results(self, db):
        """Test getting results from the latest run."""
        # Create two runs
        run1 = db.create_run()
        run1.total_tests = 1
        run1.passed = 1
        db.add_result(TestResult(
            run_id=run1.id,
            test_name="test_first",
            status=TestStatus.PASSED,
        ))
        db.finish_run(run1)

        run2 = db.create_run()
        run2.total_tests = 1
        run2.failed = 1
        db.add_result(TestResult(
            run_id=run2.id,
            test_name="test_second",
            status=TestStatus.FAILED,
        ))
        db.finish_run(run2)

        # Should get the second (latest) run
        results = db.get_latest_run_results()
        assert len(results["results"]) == 1
        assert results["results"][0]["test_name"] == "test_second"

    def test_get_recent_runs(self, db):
        """Test getting recent runs."""
        for i in range(5):
            run = db.create_run(commit_hash=f"commit{i}")
            db.finish_run(run)

        runs = db.get_recent_runs(limit=3)
        assert len(runs) == 3

    def test_test_history_tracking(self, db):
        """Test that test history is tracked."""
        run = db.create_run()

        # Add a failing test
        db.add_result(TestResult(
            run_id=run.id,
            test_name="test_flaky",
            status=TestStatus.FAILED,
        ))

        # Check history
        history = db.get_test_history("test_flaky")
        assert history is not None
        assert history.failure_count == 1
        assert history.total_runs == 1

        # Add another run
        run2 = db.create_run()
        db.add_result(TestResult(
            run_id=run2.id,
            test_name="test_flaky",
            status=TestStatus.PASSED,
        ))

        # Check updated history
        history = db.get_test_history("test_flaky")
        assert history.failure_count == 1
        assert history.total_runs == 2

    def test_get_flaky_tests(self, db):
        """Test getting flaky tests."""
        run = db.create_run()

        # Add tests with different failure rates
        for i in range(10):
            db.add_result(TestResult(
                run_id=run.id,
                test_name="test_stable",
                status=TestStatus.PASSED,
            ))

        for i in range(5):
            db.add_result(TestResult(
                run_id=run.id,
                test_name="test_flaky",
                status=TestStatus.FAILED if i < 3 else TestStatus.PASSED,
            ))

        flaky = db.get_flaky_tests(min_failure_rate=0.5)
        assert len(flaky) == 1
        assert flaky[0].test_name == "test_flaky"

    def test_clear_history(self, db):
        """Test clearing all history."""
        run = db.create_run()
        db.add_result(TestResult(
            run_id=run.id,
            test_name="test_example",
            status=TestStatus.PASSED,
        ))
        db.finish_run(run)

        db.clear_history()

        runs = db.get_recent_runs()
        assert len(runs) == 0
