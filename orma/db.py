"""Orma database — SQLite ledger for tracked files and version metadata.

Schema
------
files
    Canonical record per tracked file (keyed by root-relative path).

versions
    One row per saved version of a file.  The ``ref`` column is an opaque
    string whose meaning depends on the active backend (commit hash for
    Git, patch path for Delta).  ``is_base_snapshot`` is reserved for
    future compaction (Phase n+4) but defaults to FALSE for now.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORMA_DIR = ".orma"
DB_FILENAME = "ledger.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path        TEXT    NOT NULL UNIQUE,   -- path relative to tracked root
    first_tracked   TEXT    NOT NULL,          -- ISO-8601 UTC timestamp
    is_active       INTEGER NOT NULL DEFAULT 1 -- 0 = soft-deleted / untracked
);

CREATE TABLE IF NOT EXISTS versions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id          INTEGER NOT NULL REFERENCES files(id),
    version_number   INTEGER NOT NULL,
    timestamp        TEXT    NOT NULL,          -- ISO-8601 UTC
    size_bytes       INTEGER NOT NULL,
    sha256           TEXT    NOT NULL,
    patch_type       TEXT    NOT NULL,          -- e.g. 'git_commit', 'text_delta'
    ref              TEXT    NOT NULL,          -- backend-opaque reference
    is_base_snapshot INTEGER NOT NULL DEFAULT 0,-- reserved for compaction
    UNIQUE(file_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_versions_file_id
    ON versions(file_id);
"""


# ---------------------------------------------------------------------------
# Ledger class
# ---------------------------------------------------------------------------


class Ledger:
    """Thin wrapper around the SQLite ledger database."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._db_path = root_dir / ORMA_DIR / DB_FILENAME
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the ledger database and ensure schema exists."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            isolation_level="DEFERRED",
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Ledger is not open — call .open() first")
        return self._conn

    # -- files ---------------------------------------------------------------

    def ensure_file(self, rel_path: str) -> int:
        """Return the file id for *rel_path*, inserting a new row if needed."""
        row = self._db.execute(
            "SELECT id FROM files WHERE rel_path = ?", (rel_path,)
        ).fetchone()
        if row is not None:
            return row[0]

        now = datetime.now(timezone.utc).isoformat()
        cur = self._db.execute(
            "INSERT INTO files (rel_path, first_tracked) VALUES (?, ?)",
            (rel_path, now),
        )
        self._db.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_file_id(self, rel_path: str) -> int | None:
        """Return the file id for *rel_path*, or ``None`` if not tracked."""
        row = self._db.execute(
            "SELECT id FROM files WHERE rel_path = ?", (rel_path,)
        ).fetchone()
        return row[0] if row else None

    def get_file_count(self) -> int:
        """Return the number of tracked files."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM files WHERE is_active = 1"
        ).fetchone()
        return row[0]

    def get_total_versions(self) -> int:
        """Return the total number of version records."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM versions"
        ).fetchone()
        return row[0]

    def rename_file(self, old_rel: str, new_rel: str) -> None:
        """Update rel_path for a renamed/moved file."""
        self._db.execute(
            "UPDATE files SET rel_path = ? WHERE rel_path = ?",
            (new_rel, old_rel),
        )
        self._db.commit()

    def deactivate_file(self, rel_path: str) -> None:
        """Mark a file as inactive (soft-delete / untracked)."""
        self._db.execute(
            "UPDATE files SET is_active = 0 WHERE rel_path = ?",
            (rel_path,),
        )
        self._db.commit()

    # -- versions ------------------------------------------------------------



    def add_version(
        self,
        file_id: int,
        version_number: int,
        size_bytes: int,
        sha256: str,
        patch_type: str,
        ref: str,
    ) -> int:
        """Insert a new version row and return its row id."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._db.execute(
            """INSERT INTO versions
               (file_id, version_number, timestamp, size_bytes,
                sha256, patch_type, ref)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_id, version_number, now, size_bytes, sha256, patch_type, ref),
        )
        self._db.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_latest_version_number(self, file_id: int) -> int:
        """Return the highest version number for *file_id*, or 0 if none."""
        row = self._db.execute(
            "SELECT MAX(version_number) FROM versions WHERE file_id = ?",
            (file_id,),
        ).fetchone()
        return row[0] if row[0] is not None else 0

    def get_latest_sha256(self, file_id: int) -> str | None:
        """Return the SHA-256 of the latest version, or ``None``."""
        row = self._db.execute(
            """SELECT sha256 FROM versions
               WHERE file_id = ?
               ORDER BY version_number DESC LIMIT 1""",
            (file_id,),
        ).fetchone()
        return row[0] if row else None

    def get_versions(self, file_id: int) -> list[tuple]:
        """Return all versions for *file_id*, newest first.

        Each row is (version_number, timestamp, size_bytes, sha256, ref).
        """
        return self._db.execute(
            """SELECT version_number, timestamp, size_bytes, sha256, ref
               FROM versions
               WHERE file_id = ?
               ORDER BY version_number DESC""",
            (file_id,),
        ).fetchall()
