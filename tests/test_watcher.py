"""Tests for the debounced filesystem watcher (orma.watcher)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

from watchdog.events import DirModifiedEvent, FileModifiedEvent

from orma.watcher import DirectoryWatcher, _DebouncedHandler


def test_handler_ignores_directory_events(tmp_path: Path) -> None:
    """Directory modification events should be silently dropped."""
    callback = MagicMock()
    handler = _DebouncedHandler(tmp_path, callback, debounce_seconds=0.05)

    event = DirModifiedEvent(str(tmp_path / "subdir"))
    handler.on_modified(event)

    time.sleep(0.1)
    callback.assert_not_called()



def test_handler_ignores_orma_dir(tmp_path: Path) -> None:
    """Files inside .orma/ should never trigger a callback."""
    callback = MagicMock()
    handler = _DebouncedHandler(tmp_path, callback, debounce_seconds=0.05)

    orma_file = tmp_path / ".orma" / "ledger.db"
    orma_file.parent.mkdir()
    orma_file.touch()

    event = FileModifiedEvent(str(orma_file))
    handler.on_modified(event)

    time.sleep(0.1)
    callback.assert_not_called()


def test_handler_ignores_git_dir(tmp_path: Path) -> None:
    """Files inside .git/ should never trigger a callback."""
    callback = MagicMock()
    handler = _DebouncedHandler(tmp_path, callback, debounce_seconds=0.05)

    git_file = tmp_path / ".git" / "index"
    git_file.parent.mkdir()
    git_file.touch()

    event = FileModifiedEvent(str(git_file))
    handler.on_modified(event)

    time.sleep(0.1)
    callback.assert_not_called()


def test_handler_fires_callback_after_debounce(tmp_path: Path) -> None:
    """A single file modification should trigger the callback once."""
    callback = MagicMock()
    handler = _DebouncedHandler(tmp_path, callback, debounce_seconds=0.05)

    target = tmp_path / "hello.txt"
    target.touch()

    event = FileModifiedEvent(str(target))
    handler.on_modified(event)

    # Should NOT have fired yet (within debounce window)
    callback.assert_not_called()

    # Wait for debounce to expire
    time.sleep(0.15)
    callback.assert_called_once_with(target)


def test_handler_debounces_rapid_saves(tmp_path: Path) -> None:
    """Multiple rapid saves to the same file should coalesce into one call."""
    callback = MagicMock()
    handler = _DebouncedHandler(tmp_path, callback, debounce_seconds=0.1)

    target = tmp_path / "rapid.txt"
    target.touch()

    event = FileModifiedEvent(str(target))

    # Simulate 5 rapid saves over 50ms
    for _ in range(5):
        handler.on_modified(event)
        time.sleep(0.01)

    # Wait for debounce to expire
    time.sleep(0.2)
    callback.assert_called_once_with(target)


def test_handler_tracks_different_files_independently(
    tmp_path: Path,
) -> None:
    """Changes to different files should produce independent callbacks."""
    callback = MagicMock()
    handler = _DebouncedHandler(tmp_path, callback, debounce_seconds=0.05)

    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.touch()
    file_b.touch()

    handler.on_modified(FileModifiedEvent(str(file_a)))
    handler.on_modified(FileModifiedEvent(str(file_b)))

    time.sleep(0.15)
    assert callback.call_count == 2


def test_cancel_all_prevents_pending_callbacks(tmp_path: Path) -> None:
    """cancel_all() should prevent queued timers from firing."""
    callback = MagicMock()
    handler = _DebouncedHandler(tmp_path, callback, debounce_seconds=0.1)

    target = tmp_path / "cancel_me.txt"
    target.touch()

    handler.on_modified(FileModifiedEvent(str(target)))
    handler.cancel_all()

    time.sleep(0.2)
    callback.assert_not_called()


def test_directory_watcher_lifecycle(tmp_path: Path) -> None:
    """DirectoryWatcher should start and stop without errors."""
    callback = MagicMock()
    watcher = DirectoryWatcher(tmp_path, callback, debounce_seconds=0.05)

    watcher.start()
    time.sleep(0.1)  # let observer thread spin up
    watcher.stop()
    # No assertion — just verifying clean start/stop without exceptions
