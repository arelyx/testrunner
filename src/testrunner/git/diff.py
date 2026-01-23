"""Git diff analysis for identifying changed files and code."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import git
from git import Repo
from git.exc import InvalidGitRepositoryError, GitCommandError


@dataclass
class ChangedFile:
    """Represents a changed file in a git diff."""

    path: str
    change_type: str  # 'A' (added), 'M' (modified), 'D' (deleted), 'R' (renamed)
    additions: int = 0
    deletions: int = 0
    diff_content: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "additions": self.additions,
            "deletions": self.deletions,
            "diff_content": self.diff_content[:1000] if self.diff_content else "",
        }


@dataclass
class CommitInfo:
    """Information about a commit."""

    hash: str
    short_hash: str
    message: str
    author: str
    date: str
    files_changed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "short_hash": self.short_hash,
            "message": self.message,
            "author": self.author,
            "date": self.date,
            "files_changed": self.files_changed,
        }


class GitDiffAnalyzer:
    """Analyzes git diffs to identify changed files and code."""

    def __init__(self, repo_path: Path | str):
        """Initialize with repository path."""
        self.repo_path = Path(repo_path)
        self._repo: Optional[Repo] = None

    @property
    def repo(self) -> Repo:
        """Get the git repository, initializing if needed."""
        if self._repo is None:
            try:
                self._repo = Repo(self.repo_path, search_parent_directories=True)
            except InvalidGitRepositoryError:
                raise ValueError(f"Not a git repository: {self.repo_path}")
        return self._repo

    def get_current_commit(self) -> Optional[str]:
        """Get the current commit hash."""
        try:
            return self.repo.head.commit.hexsha
        except Exception:
            return None

    def get_current_branch(self) -> Optional[str]:
        """Get the current branch name."""
        try:
            return self.repo.active_branch.name
        except Exception:
            return None

    def analyze(
        self,
        compare_ref: str = "HEAD~5",
        include_uncommitted: bool = True,
    ) -> dict[str, Any]:
        """Analyze changes between commits and/or working directory.

        Args:
            compare_ref: Git ref to compare against (e.g., 'HEAD~5', 'main', commit hash)
            include_uncommitted: Include uncommitted changes in analysis

        Returns:
            Dictionary containing changed files, commits, and analysis
        """
        result = {
            "current_commit": self.get_current_commit(),
            "current_branch": self.get_current_branch(),
            "compare_ref": compare_ref,
            "files": [],
            "commits": [],
            "summary": {
                "total_files_changed": 0,
                "total_additions": 0,
                "total_deletions": 0,
            },
        }

        # Get committed changes
        try:
            committed_files = self._get_committed_changes(compare_ref)
            result["files"].extend(committed_files)
        except GitCommandError as e:
            # Reference might not exist (e.g., not enough commits)
            pass

        # Get uncommitted changes
        if include_uncommitted:
            uncommitted_files = self._get_uncommitted_changes()
            # Merge with committed changes, avoiding duplicates
            existing_paths = {f["path"] for f in result["files"]}
            for f in uncommitted_files:
                if f["path"] not in existing_paths:
                    result["files"].append(f)

        # Get recent commits
        try:
            commits = self._get_recent_commits(compare_ref)
            result["commits"] = commits
        except GitCommandError:
            pass

        # Calculate summary
        result["summary"]["total_files_changed"] = len(result["files"])
        result["summary"]["total_additions"] = sum(
            f.get("additions", 0) for f in result["files"]
        )
        result["summary"]["total_deletions"] = sum(
            f.get("deletions", 0) for f in result["files"]
        )

        return result

    def _get_committed_changes(self, compare_ref: str) -> list[dict]:
        """Get changes between HEAD and compare_ref."""
        files = []

        try:
            # Get the diff between HEAD and compare_ref
            diff = self.repo.head.commit.diff(compare_ref)

            for d in diff:
                change_type = d.change_type
                path = d.b_path if d.b_path else d.a_path

                # Get diff content
                diff_content = ""
                try:
                    diff_content = d.diff.decode("utf-8", errors="replace") if d.diff else ""
                except Exception:
                    pass

                changed_file = ChangedFile(
                    path=path,
                    change_type=change_type,
                    diff_content=diff_content,
                )
                files.append(changed_file.to_dict())

        except Exception:
            pass

        return files

    def _get_uncommitted_changes(self) -> list[dict]:
        """Get uncommitted changes (staged and unstaged)."""
        files = []

        # Staged changes
        try:
            staged = self.repo.index.diff("HEAD")
            for d in staged:
                path = d.b_path if d.b_path else d.a_path
                changed_file = ChangedFile(
                    path=path,
                    change_type=d.change_type,
                )
                files.append(changed_file.to_dict())
        except Exception:
            pass

        # Unstaged changes
        try:
            unstaged = self.repo.index.diff(None)
            existing_paths = {f["path"] for f in files}
            for d in unstaged:
                path = d.b_path if d.b_path else d.a_path
                if path not in existing_paths:
                    changed_file = ChangedFile(
                        path=path,
                        change_type=d.change_type,
                    )
                    files.append(changed_file.to_dict())
        except Exception:
            pass

        # Untracked files
        try:
            for path in self.repo.untracked_files:
                changed_file = ChangedFile(
                    path=path,
                    change_type="A",
                )
                files.append(changed_file.to_dict())
        except Exception:
            pass

        return files

    def _get_recent_commits(self, compare_ref: str) -> list[dict]:
        """Get recent commits since compare_ref."""
        commits = []

        try:
            # Parse the compare_ref to handle HEAD~N format
            if compare_ref.startswith("HEAD~"):
                try:
                    n = int(compare_ref[5:])
                    commit_list = list(self.repo.iter_commits("HEAD", max_count=n))
                except ValueError:
                    commit_list = list(self.repo.iter_commits(f"{compare_ref}..HEAD"))
            else:
                commit_list = list(self.repo.iter_commits(f"{compare_ref}..HEAD"))

            for commit in commit_list:
                files_changed = []
                try:
                    if commit.parents:
                        diff = commit.diff(commit.parents[0])
                        files_changed = [
                            d.b_path if d.b_path else d.a_path for d in diff
                        ]
                except Exception:
                    pass

                commit_info = CommitInfo(
                    hash=commit.hexsha,
                    short_hash=commit.hexsha[:8],
                    message=commit.message.strip(),
                    author=str(commit.author),
                    date=commit.committed_datetime.isoformat(),
                    files_changed=files_changed,
                )
                commits.append(commit_info.to_dict())

        except Exception:
            pass

        return commits

    def get_file_history(self, file_path: str, limit: int = 10) -> list[dict]:
        """Get commit history for a specific file."""
        commits = []

        try:
            for commit in self.repo.iter_commits(paths=file_path, max_count=limit):
                commit_info = CommitInfo(
                    hash=commit.hexsha,
                    short_hash=commit.hexsha[:8],
                    message=commit.message.strip(),
                    author=str(commit.author),
                    date=commit.committed_datetime.isoformat(),
                    files_changed=[file_path],
                )
                commits.append(commit_info.to_dict())
        except Exception:
            pass

        return commits

    def get_blame(self, file_path: str) -> list[dict]:
        """Get blame information for a file."""
        blame_info = []

        try:
            for commit, lines in self.repo.blame("HEAD", file_path):
                blame_info.append({
                    "commit": commit.hexsha[:8],
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "lines": len(lines),
                })
        except Exception:
            pass

        return blame_info
