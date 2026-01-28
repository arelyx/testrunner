"""SQLite database for storing test results and history."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from testrunner.storage.models import TestHistory, TestResult, TestRun, TestStatus


class Database:
    """SQLite database for test history and results."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str):
        """Initialize database connection."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._connection() as conn:
            cursor = conn.cursor()

            # Schema version tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)

            # Test runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    commit_hash TEXT,
                    branch TEXT,
                    total_tests INTEGER DEFAULT 0,
                    passed INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    skipped INTEGER DEFAULT 0
                )
            """)

            # Test results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER REFERENCES test_runs(id) ON DELETE CASCADE,
                    test_name TEXT NOT NULL,
                    test_file TEXT,
                    status TEXT NOT NULL,
                    duration_ms INTEGER DEFAULT 0,
                    output TEXT,
                    error_message TEXT,
                    risk_score REAL DEFAULT 0.0
                )
            """)

            # Create index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_test_results_run_id
                ON test_results(run_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_test_results_name
                ON test_results(test_name)
            """)

            # Test history table (aggregated statistics)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_history (
                    test_name TEXT PRIMARY KEY,
                    last_failed_at TIMESTAMP,
                    failure_count INTEGER DEFAULT 0,
                    total_runs INTEGER DEFAULT 0,
                    avg_duration_ms REAL DEFAULT 0.0
                )
            """)

            # Risk analysis cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_analysis (
                    test_name TEXT PRIMARY KEY,
                    risk_score REAL DEFAULT 0.0,
                    risk_factors TEXT,
                    affected_by_changes INTEGER DEFAULT 0,
                    updated_at TIMESTAMP
                )
            """)

            conn.commit()

    def create_run(
        self,
        commit_hash: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> TestRun:
        """Create a new test run."""
        with self._connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()

            cursor.execute(
                """
                INSERT INTO test_runs (started_at, commit_hash, branch)
                VALUES (?, ?, ?)
                """,
                (now.isoformat(), commit_hash, branch),
            )

            run_id = cursor.lastrowid
            return TestRun(
                id=run_id,
                started_at=now,
                commit_hash=commit_hash,
                branch=branch,
            )

    def finish_run(self, run: TestRun) -> None:
        """Mark a test run as finished and update statistics."""
        with self._connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()

            cursor.execute(
                """
                UPDATE test_runs
                SET finished_at = ?,
                    total_tests = ?,
                    passed = ?,
                    failed = ?,
                    skipped = ?
                WHERE id = ?
                """,
                (
                    now.isoformat(),
                    run.total_tests,
                    run.passed,
                    run.failed,
                    run.skipped,
                    run.id,
                ),
            )

    def add_result(self, result: TestResult) -> TestResult:
        """Add a test result."""
        with self._connection() as conn:
            cursor = conn.cursor()

            status_value = (
                result.status.value
                if isinstance(result.status, TestStatus)
                else result.status
            )

            cursor.execute(
                """
                INSERT INTO test_results
                (run_id, test_name, test_file, status, duration_ms, output, error_message, risk_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.test_name,
                    result.test_file,
                    status_value,
                    result.duration_ms,
                    result.output,
                    result.error_message,
                    result.risk_score,
                ),
            )

            result.id = cursor.lastrowid

            # Update test history
            self._update_test_history(cursor, result)

            return result

    def _update_test_history(
        self, cursor: sqlite3.Cursor, result: TestResult
    ) -> None:
        """Update test history with new result."""
        # Get current history
        cursor.execute(
            "SELECT * FROM test_history WHERE test_name = ?",
            (result.test_name,),
        )
        row = cursor.fetchone()

        now = datetime.now()
        is_failure = result.status in (TestStatus.FAILED, TestStatus.ERROR)

        if row:
            # Update existing history
            total_runs = row["total_runs"] + 1
            failure_count = row["failure_count"] + (1 if is_failure else 0)
            avg_duration = (
                (row["avg_duration_ms"] * row["total_runs"] + result.duration_ms)
                / total_runs
            )

            cursor.execute(
                """
                UPDATE test_history
                SET last_failed_at = CASE WHEN ? THEN ? ELSE last_failed_at END,
                    failure_count = ?,
                    total_runs = ?,
                    avg_duration_ms = ?
                WHERE test_name = ?
                """,
                (
                    is_failure,
                    now.isoformat() if is_failure else None,
                    failure_count,
                    total_runs,
                    avg_duration,
                    result.test_name,
                ),
            )
        else:
            # Create new history entry
            cursor.execute(
                """
                INSERT INTO test_history
                (test_name, last_failed_at, failure_count, total_runs, avg_duration_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.test_name,
                    now.isoformat() if is_failure else None,
                    1 if is_failure else 0,
                    1,
                    float(result.duration_ms),
                ),
            )

    def get_run(self, run_id: int) -> Optional[TestRun]:
        """Get a test run by ID."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()

            if row:
                return TestRun.from_row(tuple(row))
            return None

    def get_run_results(self, run_id: int) -> dict:
        """Get all results for a test run."""
        with self._connection() as conn:
            cursor = conn.cursor()

            # Get run info
            cursor.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,))
            run_row = cursor.fetchone()

            if not run_row:
                return {}

            run = TestRun.from_row(tuple(run_row))

            # Get test results
            cursor.execute(
                "SELECT * FROM test_results WHERE run_id = ? ORDER BY risk_score DESC",
                (run_id,),
            )
            results = [TestResult.from_row(tuple(row)) for row in cursor.fetchall()]

            return {
                "run": run.to_dict(),
                "total": run.total_tests,
                "passed": run.passed,
                "failed": run.failed,
                "skipped": run.skipped,
                "results": [r.to_dict() for r in results],
                "failed_tests": [r.to_dict() for r in results if r.status == TestStatus.FAILED],
                "passed_tests": [r.to_dict() for r in results if r.status == TestStatus.PASSED],
            }

    def get_latest_run_results(self) -> dict:
        """Get results from the most recent test run."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM test_runs ORDER BY started_at DESC LIMIT 1"
            )
            row = cursor.fetchone()

            if row:
                return self.get_run_results(row[0])
            return {}

    def get_recent_runs(self, limit: int = 10) -> list[TestRun]:
        """Get recent test runs."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM test_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            return [TestRun.from_row(tuple(row)) for row in cursor.fetchall()]

    def get_test_history(self, test_name: str) -> Optional[TestHistory]:
        """Get history for a specific test."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM test_history WHERE test_name = ?",
                (test_name,),
            )
            row = cursor.fetchone()

            if row:
                return TestHistory.from_row(tuple(row))
            return None

    def get_all_test_history(self) -> list[TestHistory]:
        """Get history for all tests."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM test_history ORDER BY failure_count DESC"
            )
            return [TestHistory.from_row(tuple(row)) for row in cursor.fetchall()]

    def get_flaky_tests(self, min_failure_rate: float = 0.1) -> list[TestHistory]:
        """Get tests with high failure rates."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM test_history
                WHERE total_runs > 1
                AND CAST(failure_count AS REAL) / total_runs >= ?
                ORDER BY CAST(failure_count AS REAL) / total_runs DESC
                """,
                (min_failure_rate,),
            )
            return [TestHistory.from_row(tuple(row)) for row in cursor.fetchall()]

    def get_recently_failed_tests(self, days: int = 7) -> list[TestHistory]:
        """Get tests that failed recently."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM test_history
                WHERE last_failed_at IS NOT NULL
                AND datetime(last_failed_at) >= datetime('now', '-' || ? || ' days')
                ORDER BY last_failed_at DESC
                """,
                (days,),
            )
            return [TestHistory.from_row(tuple(row)) for row in cursor.fetchall()]

    def clear_history(self) -> None:
        """Clear all test history (for testing purposes)."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM test_results")
            cursor.execute("DELETE FROM test_runs")
            cursor.execute("DELETE FROM test_history")
            cursor.execute("DELETE FROM risk_analysis")
