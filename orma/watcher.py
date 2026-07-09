"""Orma watcher — debounced filesystem event handler using watchdog.

Watches a directory for file modifications and fires a callback after a
per-file debounce window.  Rapid successive saves to the same file are
coalesced into a single callback invocation.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from orma.db import ORMA_DIR
from orma.ignore import is_ignored, load_ignore_patterns

logger = logging.getLogger(__name__)

# Directories that should never trigger versioning
_IGNORE_DIRS = frozenset({ORMA_DIR, ".orma-versions", ".git"})

# Default debounce window in seconds
DEFAULT_DEBOUNCE_SECONDS = 0.5


class _DebouncedHandler(FileSystemEventHandler):
    """Watchdog handler that debounces per-file modification events.

    For each modified file, a timer is (re)started.  Only when the timer
    expires without being reset does ``on_file_change`` fire.
    """

    def __init__(
        self,
        root_dir: Path,
        on_file_change: Callable[[Path], None],
        on_file_delete: Callable[[Path], None] | None = None,
        on_file_move: Callable[[Path, Path], None] | None = None,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        super().__init__()
        self._root_dir = root_dir
        self._on_file_change = on_file_change
        self._on_file_delete = on_file_delete
        self._on_file_move = on_file_move
        self._debounce_seconds = debounce_seconds
        self._timers: dict[Path, threading.Timer] = {}
        self._lock = threading.Lock()
        self._ignore_patterns = load_ignore_patterns(root_dir)

    def _should_ignore(self, path: Path) -> bool:
        """Return True if *path* should be skipped."""
        try:
            rel = path.relative_to(self._root_dir)
        except ValueError:
            return True
        if any(part in _IGNORE_DIRS for part in rel.parts):
            return True
        return is_ignored(str(rel), self._ignore_patterns)

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_ignore(path):
            return
        self._schedule(path)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(event.src_path)
        if self._should_ignore(path):
            return
        # Treat new files the same as modifications
        self._schedule(path)

    def on_deleted(self, event: FileDeletedEvent) -> None:  # type: ignore[override]
        if event.is_directory or self._on_file_delete is None:
            return
        path = Path(event.src_path)
        if self._should_ignore(path):
            return
        logger.debug("file deleted: %s", path)
        try:
            self._on_file_delete(path)
        except Exception:
            logger.exception("error handling delete: %s", path)

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        if event.is_directory or self._on_file_move is None:
            return
        src = Path(event.src_path)
        dest = Path(event.dest_path)
        if self._should_ignore(src) and self._should_ignore(dest):
            return
        logger.debug("file moved: %s -> %s", src, dest)
        try:
            self._on_file_move(src, dest)
        except Exception:
            logger.exception("error handling move: %s", src)

    # -- debounce logic ------------------------------------------------------

    def _schedule(self, path: Path) -> None:
        """(Re)start the debounce timer for *path*."""
        with self._lock:
            existing = self._timers.get(path)
            if existing is not None:
                existing.cancel()

            timer = threading.Timer(
                self._debounce_seconds,
                self._fire,
                args=(path,),
            )
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: Path) -> None:
        """Called when the debounce window expires — invoke the callback."""
        with self._lock:
            self._timers.pop(path, None)

        logger.debug("file change detected: %s", path)
        try:
            self._on_file_change(path)
        except Exception:
            logger.exception("error handling file change: %s", path)

    def cancel_all(self) -> None:
        """Cancel every pending timer (used during shutdown)."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


class DirectoryWatcher:
    """Watches *root_dir* for file changes and invokes *on_file_change*.

    Usage::

        def handle(path: Path) -> None:
            print(f"changed: {path}")

        watcher = DirectoryWatcher(Path("/my/project"), handle)
        watcher.start()   # non-blocking
        ...
        watcher.stop()    # blocks until observer thread joins
    """

    def __init__(
        self,
        root_dir: Path,
        on_file_change: Callable[[Path], None],
        on_file_delete: Callable[[Path], None] | None = None,
        on_file_move: Callable[[Path, Path], None] | None = None,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        self._root_dir = root_dir
        self._handler = _DebouncedHandler(
            root_dir,
            on_file_change,
            on_file_delete=on_file_delete,
            on_file_move=on_file_move,
            debounce_seconds=debounce_seconds,
        )
        self._observer = Observer()
        self._observer.schedule(
            self._handler, str(root_dir), recursive=True
        )

    def start(self) -> None:
        """Start watching (non-blocking — spawns a background thread)."""
        logger.info("watching: %s", self._root_dir)
        self._observer.start()

    def stop(self) -> None:
        """Stop watching and wait for the observer thread to finish."""
        self._handler.cancel_all()
        self._observer.stop()
        self._observer.join()
        logger.info("stopped watching: %s", self._root_dir)
