"""Orma ignore — .ormaignore glob pattern matching.

Reads a ``.ormaignore`` file from the tracked root and provides a
function to test whether a relative path should be skipped.  Syntax
mirrors ``.gitignore`` (one glob per line, ``#`` comments, blank lines
ignored).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

ORMAIGNORE_FILE = ".ormaignore"


def load_ignore_patterns(root_dir: Path) -> list[str]:
    """Read ``.ormaignore`` from *root_dir* and return glob patterns.

    Returns an empty list if the file does not exist.
    """
    ignore_path = root_dir / ORMAIGNORE_FILE
    if not ignore_path.is_file():
        return []

    patterns: list[str] = []
    for line in ignore_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    """Return True if *rel_path* matches any ignore pattern.

    Matching is done against both the full relative path and the
    basename, so ``*.log`` matches ``debug.log`` as well as
    ``logs/debug.log``.
    """
    parts = Path(rel_path).parts
    basename = parts[-1] if parts else ""

    for pattern in patterns:
        # Match against full relative path
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # Match against basename only
        if fnmatch.fnmatch(basename, pattern):
            return True
        # Match against any directory component
        if any(fnmatch.fnmatch(part, pattern) for part in parts[:-1]):
            return True
    return False
