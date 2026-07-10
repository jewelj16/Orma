"""Tests for edge-case handling in GitBackend."""

from __future__ import annotations

from pathlib import Path

from orma.backends.git_backend import GitBackend


def test_symlinks_are_skipped(tmp_path: Path) -> None:
    """Symlinks should be silently skipped, not crash."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        real = tmp_path / "real.txt"
        real.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to(real)

        result = backend.on_file_saved(link)
        assert result.saved is False
    finally:
        backend.close()


def test_large_files_are_skipped(tmp_path: Path, monkeypatch) -> None:
    """Files exceeding MAX_FILE_BYTES should be skipped with a warning."""
    import orma.backends.git_backend as mod

    monkeypatch.setattr(mod, "MAX_FILE_BYTES", 100)

    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        big = tmp_path / "big.bin"
        big.write_bytes(b"x" * 200)

        result = backend.on_file_saved(big)
        assert result.saved is False
    finally:
        backend.close()


def test_permission_denied_is_handled(tmp_path: Path) -> None:
    """Files that can't be read should be skipped, not crash."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        secret = tmp_path / "noperm.txt"
        secret.write_text("secret")
        secret.chmod(0o000)

        result = backend.on_file_saved(secret)
        assert result.saved is False
    finally:
        # Restore permissions for cleanup
        secret.chmod(0o644)
        backend.close()


def test_disappeared_file_is_handled(tmp_path: Path) -> None:
    """File removed between event and handler should not crash."""
    backend = GitBackend()
    backend.init_tracking(tmp_path)
    try:
        ghost = tmp_path / "ghost.txt"
        ghost.write_text("here now")

        # Remove before on_file_saved can stat it
        ghost.unlink()

        result = backend.on_file_saved(ghost)
        assert result.saved is False
    finally:
        backend.close()
