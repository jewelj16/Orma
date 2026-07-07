"""Tests for GitBackend (orma.backends.git_backend)."""

from __future__ import annotations

from pathlib import Path

from orma.backends.git_backend import GitBackend


def test_init_tracking_creates_hidden_repo(tmp_path: Path) -> None:
    """init_tracking should create .orma/repo.git and ledger.db."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        assert (tmp_path / ".orma" / "repo.git" / "HEAD").exists()
        assert (tmp_path / ".orma" / "ledger.db").exists()
    finally:
        backend.close()


def test_init_tracking_is_idempotent(tmp_path: Path) -> None:
    """Calling init_tracking twice should not error."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    backend.close()

    backend2 = GitBackend()
    backend2.init_tracking(tmp_path)
    backend2.close()


def test_on_file_saved_creates_version(tmp_path: Path) -> None:
    """Saving a file should create version 1 in the ledger."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        result = backend.on_file_saved(f)
        assert result.saved is True
        assert result.version_number == 1
        assert len(result.sha256) == 64  # SHA-256 hex
    finally:
        backend.close()


def test_on_file_saved_detects_noop(tmp_path: Path) -> None:
    """Saving an unchanged file should return saved=False."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        backend.on_file_saved(f)

        # Save again without changing
        result = backend.on_file_saved(f)
        assert result.saved is False
        assert result.version_number == 1
    finally:
        backend.close()


def test_multiple_versions(tmp_path: Path) -> None:
    """Successive edits should produce incrementing version numbers."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        f = tmp_path / "counter.txt"

        for i in range(1, 4):
            f.write_text(f"version {i}")
            result = backend.on_file_saved(f)
            assert result.saved is True
            assert result.version_number == i
    finally:
        backend.close()


def test_get_history(tmp_path: Path) -> None:
    """get_history should return all versions, newest first."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        f = tmp_path / "log.txt"
        f.write_text("first")
        backend.on_file_saved(f)
        f.write_text("second")
        backend.on_file_saved(f)

        history = backend.get_history(f)
        assert len(history) == 2
        assert history[0].version_number == 2
        assert history[1].version_number == 1
    finally:
        backend.close()


def test_get_history_unknown_file(tmp_path: Path) -> None:
    """get_history on an untracked file should return empty list."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        f = tmp_path / "ghost.txt"
        assert backend.get_history(f) == []
    finally:
        backend.close()


def test_reconstruct_version(tmp_path: Path) -> None:
    """reconstruct_version should return exact file content at that version."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        f = tmp_path / "data.txt"

        f.write_text("alpha")
        backend.on_file_saved(f)

        f.write_text("beta")
        backend.on_file_saved(f)

        f.write_text("gamma")
        backend.on_file_saved(f)

        assert backend.reconstruct_version(f, 1) == b"alpha"
        assert backend.reconstruct_version(f, 2) == b"beta"
        assert backend.reconstruct_version(f, 3) == b"gamma"
    finally:
        backend.close()


def test_reconstruct_version_not_found(tmp_path: Path) -> None:
    """Requesting a nonexistent version should raise ValueError."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        f = tmp_path / "data.txt"
        f.write_text("only version")
        backend.on_file_saved(f)

        import pytest

        with pytest.raises(ValueError, match="version 99"):
            backend.reconstruct_version(f, 99)
    finally:
        backend.close()


def test_multiple_files_independent(tmp_path: Path) -> None:
    """Different files should have independent version numbering."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"

        a.write_text("a1")
        backend.on_file_saved(a)

        b.write_text("b1")
        backend.on_file_saved(b)

        a.write_text("a2")
        result_a = backend.on_file_saved(a)

        assert result_a.version_number == 2
        assert len(backend.get_history(a)) == 2
        assert len(backend.get_history(b)) == 1
    finally:
        backend.close()
