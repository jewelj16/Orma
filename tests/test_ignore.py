"""Tests for .ormaignore support (orma.ignore)."""

from __future__ import annotations

from pathlib import Path

from orma.ignore import is_ignored, load_ignore_patterns


def test_load_patterns_missing_file(tmp_path: Path) -> None:
    """No .ormaignore → empty list."""
    assert load_ignore_patterns(tmp_path) == []


def test_load_patterns_basic(tmp_path: Path) -> None:
    """Parses patterns, skips comments and blank lines."""
    (tmp_path / ".ormaignore").write_text(
        "*.log\n"
        "\n"
        "# build artifacts\n"
        "dist/\n"
        "  node_modules  \n"
    )
    patterns = load_ignore_patterns(tmp_path)
    assert patterns == ["*.log", "dist/", "node_modules"]


def test_is_ignored_by_extension() -> None:
    """*.log should match any .log file at any depth."""
    patterns = ["*.log"]
    assert is_ignored("debug.log", patterns)
    assert is_ignored("logs/debug.log", patterns)
    assert not is_ignored("main.py", patterns)


def test_is_ignored_by_directory() -> None:
    """A directory pattern should match files under that directory."""
    patterns = ["node_modules"]
    assert is_ignored("node_modules/pkg/index.js", patterns)
    assert not is_ignored("src/main.js", patterns)


def test_is_ignored_by_full_path() -> None:
    """Exact relative path matching."""
    patterns = ["build/output.bin"]
    assert is_ignored("build/output.bin", patterns)
    assert not is_ignored("output.bin", patterns)


def test_multiple_patterns() -> None:
    """All patterns are checked; any match → ignored."""
    patterns = ["*.pyc", "__pycache__", "*.egg-info"]
    assert is_ignored("orma/__pycache__/cli.cpython-312.pyc", patterns)
    assert is_ignored("module.pyc", patterns)
    assert is_ignored("orma.egg-info/PKG-INFO", patterns)
    assert not is_ignored("orma/cli.py", patterns)
