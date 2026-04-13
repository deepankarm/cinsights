from __future__ import annotations

import logging
from pathlib import Path

from dulwich.repo import Repo

logger = logging.getLogger(__name__)


class GitReader:
    """Read checkpoint data from an Entire.co orphan branch using dulwich."""

    def __init__(self, repo_path: Path, branch: str = "entire/checkpoints/v1"):
        self.repo_path = repo_path
        self.branch = branch
        self._repo: Repo | None = None
        self._tree_cache: dict[str, bytes] | None = None

    def _get_repo(self) -> Repo:
        if self._repo is None:
            self._repo = Repo(str(self.repo_path))
        return self._repo

    def _resolve_branch_tree(self) -> bytes | None:
        """Resolve the branch ref to its root tree SHA."""
        repo = self._get_repo()
        ref = f"refs/heads/{self.branch}".encode()
        try:
            commit_sha = repo.refs[ref]
        except KeyError:
            return None
        commit = repo[commit_sha]
        return commit.tree

    def branch_exists(self) -> bool:
        return self._resolve_branch_tree() is not None

    def _build_tree_cache(self) -> dict[str, bytes]:
        """Walk the full tree once, cache path → blob SHA."""
        if self._tree_cache is not None:
            return self._tree_cache

        tree_sha = self._resolve_branch_tree()
        if tree_sha is None:
            self._tree_cache = {}
            return self._tree_cache

        repo = self._get_repo()
        cache: dict[str, bytes] = {}

        def _walk(tree_id: bytes, prefix: str) -> None:
            tree = repo[tree_id]
            for item in tree.items():
                name = item.path.decode()
                full_path = f"{prefix}{name}" if prefix else name
                mode = item.mode
                if mode & 0o40000:  # directory
                    _walk(item.sha, f"{full_path}/")
                else:
                    cache[full_path] = item.sha

        _walk(tree_sha, "")
        self._tree_cache = cache
        return cache

    def list_checkpoint_dirs(self) -> list[str]:
        """List checkpoint directory paths (e.g., 'a1/b2c3d4e5f6')."""
        cache = self._build_tree_cache()
        checkpoint_dirs: set[str] = set()
        for path in cache:
            parts = path.split("/")
            if len(parts) == 3 and parts[2] == "metadata.json":
                checkpoint_dirs.add(f"{parts[0]}/{parts[1]}")
        return sorted(checkpoint_dirs)

    def read_file(self, path: str) -> bytes:
        """Read a file from the checkpoint branch."""
        cache = self._build_tree_cache()
        blob_sha = cache.get(path)
        if blob_sha is None:
            raise FileNotFoundError(f"{path} not found on {self.branch}")
        repo = self._get_repo()
        return repo[blob_sha].data

    def read_file_text(self, path: str) -> str:
        return self.read_file(path).decode()

    def batch_read_files(self, paths: list[str]) -> dict[str, bytes]:
        """Read multiple files efficiently using the tree cache."""
        cache = self._build_tree_cache()
        repo = self._get_repo()
        results: dict[str, bytes] = {}
        for path in paths:
            blob_sha = cache.get(path)
            if blob_sha is not None:
                results[path] = repo[blob_sha].data
        return results

    def get_commit_authors(self) -> dict[str, str]:
        """Map checkpoint paths to git author emails."""
        repo = self._get_repo()
        ref = f"refs/heads/{self.branch}".encode()
        try:
            head_sha = repo.refs[ref]
        except KeyError:
            return {}

        authors: dict[str, str] = {}
        for entry in repo.get_walker(include=[head_sha]):
            commit = entry.commit
            raw = commit.author.decode()
            email = raw.split("<")[-1].rstrip(">") if "<" in raw else raw
            subject = commit.message.decode().split("\n", 1)[0]
            for word in subject.split():
                word = word.strip("()[]:")
                if len(word) == 12 and all(c in "0123456789abcdef" for c in word):
                    checkpoint_dir = f"{word[:2]}/{word[2:]}"
                    authors[checkpoint_dir] = email
                    break

        return authors
