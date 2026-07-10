"""Git-backed version storage for Orma (Phase n-1).

Uses a hidden git-dir (``<root>/.orma/repo.git``) with the tracked
directory as the working tree, so the user's directory never shows a
visible ``.git`` folder.  Every file save becomes an atomic
``git add + git commit``, and version metadata is mirrored into the
SQLite ledger for fast queries.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from orma.backends.base import SaveResult, VersionBackend, VersionInfo
from orma.db import ORMA_DIR, Ledger

logger = logging.getLogger(__name__)

# Files larger than this are skipped with a warning (default 50 MB)
MAX_FILE_BYTES = 50 * 1024 * 1024


class GitBackend(VersionBackend):
    """VersionBackend implementation backed by a hidden Git repository."""

    def __init__(self) -> None:
        self._root_dir: Path | None = None
        self._git_dir: Path | None = None
        self._ledger: Ledger | None = None

    # -- helpers -------------------------------------------------------------

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command against the hidden repo."""
        assert self._git_dir is not None and self._root_dir is not None
        cmd = [
            "git",
            f"--git-dir={self._git_dir}",
            f"--work-tree={self._root_dir}",
            *args,
        ]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
        )

    @property
    def _db(self) -> Ledger:
        assert self._ledger is not None
        return self._ledger

    @staticmethod
    def _sha256(path: Path) -> str:
        """Compute SHA-256 hex digest of a file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _rel_path(self, path: Path) -> str:
        """Return the path relative to the tracked root."""
        return str(path.resolve().relative_to(self._root_dir.resolve()))

    # -- VersionBackend interface --------------------------------------------

    def init_tracking(self, root_dir: Path) -> None:
        """Set up a hidden git repo and open the ledger."""
        self._root_dir = root_dir.resolve()
        self._git_dir = self._root_dir / ORMA_DIR / "repo.git"

        if not self._git_dir.exists():
            self._git_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "--bare", str(self._git_dir)],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("initialized git repo: %s", self._git_dir)

        self._ledger = Ledger(self._root_dir)
        self._ledger.open()
        logger.info("tracking: %s", self._root_dir)

    def on_file_saved(self, path: Path) -> SaveResult:
        """Stage, commit, and mirror to ledger.  Skip no-op saves.

        Guards against symlinks, large files, and permission errors.
        """
        # -- edge-case guards ------------------------------------------------
        if path.is_symlink():
            logger.debug("skipping symlink: %s", path)
            return SaveResult(saved=False, version_number=0, sha256="")

        try:
            stat = path.stat()
        except (PermissionError, OSError) as exc:
            logger.warning("cannot access %s: %s", path, exc)
            return SaveResult(saved=False, version_number=0, sha256="")

        if stat.st_size > MAX_FILE_BYTES:
            logger.warning(
                "skipping large file (%d bytes > %d limit): %s",
                stat.st_size, MAX_FILE_BYTES, path,
            )
            return SaveResult(saved=False, version_number=0, sha256="")

        rel = self._rel_path(path)
        file_id = self._db.ensure_file(rel)

        # Compute hash and check for no-op
        try:
            current_hash = self._sha256(path)
        except (PermissionError, OSError) as exc:
            logger.warning("cannot read %s: %s", path, exc)
            return SaveResult(saved=False, version_number=0, sha256="")

        last_hash = self._db.get_latest_sha256(file_id)
        if current_hash == last_hash:
            ver = self._db.get_latest_version_number(file_id)
            return SaveResult(
                saved=False, version_number=ver, sha256=current_hash
            )

        # Stage and commit
        self._git("add", "--force", rel)
        next_ver = self._db.get_latest_version_number(file_id) + 1
        msg = f"v{next_ver}: {rel}"
        self._git("commit", "-m", msg, "--allow-empty")

        # Get the commit hash
        result = self._git("rev-parse", "HEAD")
        commit_hash = result.stdout.strip()

        # Mirror to ledger
        size = path.stat().st_size
        self._db.add_version(
            file_id=file_id,
            version_number=next_ver,
            size_bytes=size,
            sha256=current_hash,
            patch_type="git_commit",
            ref=commit_hash,
        )

        logger.info("saved v%d of %s (%s)", next_ver, rel, commit_hash[:8])
        return SaveResult(saved=True, version_number=next_ver, sha256=current_hash)

    def get_history(self, path: Path) -> list[VersionInfo]:
        """Return version history from the ledger, newest first."""
        rel = self._rel_path(path)
        file_id = self._db.get_file_id(rel)
        if file_id is None:
            return []

        rows = self._db.get_versions(file_id)
        return [
            VersionInfo(
                version_number=row[0],
                timestamp=datetime.fromisoformat(row[1]).replace(
                    tzinfo=timezone.utc
                ),
                size_bytes=row[2],
                sha256=row[3],
                ref=row[4],
            )
            for row in rows
        ]

    def reconstruct_version(self, path: Path, version_number: int) -> bytes:
        """Retrieve file contents at a given version via ``git show``."""
        rel = self._rel_path(path)
        file_id = self._db.get_file_id(rel)
        if file_id is None:
            msg = f"file not tracked: {rel}"
            raise FileNotFoundError(msg)

        # Find the commit ref for this version
        rows = self._db.get_versions(file_id)
        ref = None
        for row in rows:
            if row[0] == version_number:
                ref = row[4]
                break
        if ref is None:
            msg = f"version {version_number} not found for {rel}"
            raise ValueError(msg)

        result = self._git("show", f"{ref}:{rel}")
        return result.stdout.encode()

    def close(self) -> None:
        """Close the ledger database."""
        if self._ledger is not None:
            self._ledger.close()
