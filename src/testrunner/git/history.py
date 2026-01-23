"""Git history analysis for understanding code evolution."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from git import Repo
from git.exc import InvalidGitRepositoryError


@dataclass
class FileContributor:
    """Information about a file contributor."""

    name: str
    email: str
    commits: int
    lines_added: int = 0
    lines_removed: int = 0
    last_commit_date: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "email": self.email,
            "commits": self.commits,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "last_commit_date": (
                self.last_commit_date.isoformat() if self.last_commit_date else None
            ),
        }


class GitHistoryAnalyzer:
    """Analyzes git history for deeper insights."""

    def __init__(self, repo_path: Path | str):
        """Initialize with repository path."""
        self.repo_path = Path(repo_path)
        self._repo: Optional[Repo] = None

    @property
    def repo(self) -> Repo:
        """Get the git repository."""
        if self._repo is None:
            try:
                self._repo = Repo(self.repo_path, search_parent_directories=True)
            except InvalidGitRepositoryError:
                raise ValueError(f"Not a git repository: {self.repo_path}")
        return self._repo

    def get_file_contributors(self, file_path: str) -> list[FileContributor]:
        """Get contributors for a specific file."""
        contributors: dict[str, FileContributor] = {}

        try:
            for commit in self.repo.iter_commits(paths=file_path):
                key = commit.author.email
                if key not in contributors:
                    contributors[key] = FileContributor(
                        name=commit.author.name,
                        email=commit.author.email,
                        commits=0,
                    )

                contributors[key].commits += 1
                if (
                    contributors[key].last_commit_date is None
                    or commit.committed_datetime > contributors[key].last_commit_date
                ):
                    contributors[key].last_commit_date = commit.committed_datetime

        except Exception:
            pass

        return sorted(contributors.values(), key=lambda c: c.commits, reverse=True)

    def get_recently_modified_files(
        self, days: int = 7, limit: int = 50
    ) -> list[dict]:
        """Get files modified in the last N days."""
        since = datetime.now() - timedelta(days=days)
        files: dict[str, dict] = {}

        try:
            for commit in self.repo.iter_commits(since=since):
                if commit.parents:
                    diff = commit.diff(commit.parents[0])
                    for d in diff:
                        path = d.b_path if d.b_path else d.a_path
                        if path not in files:
                            files[path] = {
                                "path": path,
                                "modifications": 0,
                                "last_modified": commit.committed_datetime.isoformat(),
                                "last_author": commit.author.name,
                            }
                        files[path]["modifications"] += 1

        except Exception:
            pass

        # Sort by modifications and return top files
        sorted_files = sorted(
            files.values(), key=lambda f: f["modifications"], reverse=True
        )
        return sorted_files[:limit]

    def get_hotspot_files(self, limit: int = 20) -> list[dict]:
        """Identify hotspot files (frequently changed files)."""
        file_changes: dict[str, dict] = {}

        try:
            # Analyze last 100 commits
            for commit in self.repo.iter_commits(max_count=100):
                if commit.parents:
                    diff = commit.diff(commit.parents[0])
                    for d in diff:
                        path = d.b_path if d.b_path else d.a_path
                        if path not in file_changes:
                            file_changes[path] = {
                                "path": path,
                                "change_count": 0,
                                "unique_authors": set(),
                            }
                        file_changes[path]["change_count"] += 1
                        file_changes[path]["unique_authors"].add(commit.author.email)

        except Exception:
            pass

        # Convert sets to counts
        for f in file_changes.values():
            f["unique_authors"] = len(f["unique_authors"])

        # Sort by change count
        sorted_files = sorted(
            file_changes.values(), key=lambda f: f["change_count"], reverse=True
        )
        return sorted_files[:limit]

    def find_related_files(self, file_path: str, limit: int = 10) -> list[dict]:
        """Find files that are often changed together with the given file."""
        co_changes: dict[str, int] = {}

        try:
            # Get commits that modified the target file
            for commit in self.repo.iter_commits(paths=file_path, max_count=50):
                if commit.parents:
                    diff = commit.diff(commit.parents[0])
                    changed_files = [
                        d.b_path if d.b_path else d.a_path for d in diff
                    ]

                    # Count co-changes with other files
                    for other_file in changed_files:
                        if other_file != file_path:
                            co_changes[other_file] = co_changes.get(other_file, 0) + 1

        except Exception:
            pass

        # Sort by co-change frequency
        sorted_files = sorted(co_changes.items(), key=lambda x: x[1], reverse=True)
        return [
            {"path": path, "co_change_count": count}
            for path, count in sorted_files[:limit]
        ]

    def get_commit_frequency(self, days: int = 30) -> dict:
        """Get commit frequency over the specified period."""
        frequency = {}
        since = datetime.now() - timedelta(days=days)

        try:
            for commit in self.repo.iter_commits(since=since):
                date_key = commit.committed_datetime.strftime("%Y-%m-%d")
                frequency[date_key] = frequency.get(date_key, 0) + 1
        except Exception:
            pass

        return frequency
