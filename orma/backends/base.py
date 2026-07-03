"""Abstract base class for version-storage backends.

This is THE seam in the architecture: cli.py, watcher.py, and db.py depend
only on VersionBackend and the value objects defined here.  Swapping the
storage engine (Git → custom delta) means writing a new subclass of
VersionBackend and changing nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class SaveResult:
    """Returned by ``on_file_saved`` to describe what happened.

    Attributes:
        saved: True if a new version was stored, False if the file was
            unchanged (no-op save).
        version_number: The version number assigned (or the current latest
            version number on a no-op).
        sha256: Hex digest of the file content at this version.
    """

    saved: bool
    version_number: int
    sha256: str


@dataclass(frozen=True)
class VersionInfo:
    """One entry in a file's version history.

    Attributes:
        version_number: 1-based version ordinal.
        timestamp: When this version was recorded.
        size_bytes: File size at this version.
        sha256: Content hash for integrity and no-op detection.
        ref: Backend-opaque reference (commit hash for Git, patch path
            for Delta) — lets ``reconstruct_version`` find the data
            without the caller knowing which backend produced it.
    """

    version_number: int
    timestamp: datetime
    size_bytes: int
    sha256: str
    ref: str


class VersionBackend(ABC):
    """Abstract interface that every storage backend must implement."""

    @abstractmethod
    def init_tracking(self, root_dir: Path) -> None:
        """Prepare *root_dir* for version tracking.

        Called once when ``orma track <dir>`` is run.  The backend should
        create whatever internal structure it needs (hidden repos, patch
        directories, etc.) without leaving visible artifacts in *root_dir*
        itself.
        """

    @abstractmethod
    def on_file_saved(self, path: Path) -> SaveResult:
        """Record a new version of *path* (or detect a no-op save).

        Called by the watcher whenever a tracked file is modified.
        """

    @abstractmethod
    def get_history(self, path: Path) -> list[VersionInfo]:
        """Return the full version history for *path*, newest first."""

    @abstractmethod
    def reconstruct_version(self, path: Path, version_number: int) -> bytes:
        """Return the raw file content as it existed at *version_number*."""
