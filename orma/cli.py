"""Orma CLI — command-line interface for local file versioning."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import click

from orma import __version__
from orma.backends.git_backend import GitBackend


def _get_backend(root_dir: Path) -> GitBackend:
    """Create and initialize a GitBackend for *root_dir*."""
    backend = GitBackend()
    backend.init_tracking(root_dir)
    return backend


def _find_root(filepath: Path) -> Path | None:
    """Walk up from *filepath* to find a directory containing .orma/."""
    current = filepath if filepath.is_dir() else filepath.parent
    current = current.resolve()
    while True:
        if (current / ".orma").is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


@click.group()
@click.version_option(version=__version__, prog_name="orma")
def main() -> None:
    """Orma — remembers every save of every tracked file."""


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
def track(directory: str) -> None:
    """Start tracking a directory for automatic file versioning."""
    root = Path(directory).resolve()
    backend = _get_backend(root)
    try:
        from orma.ignore import is_ignored, load_ignore_patterns

        patterns = load_ignore_patterns(root)

        # Initial scan: version every existing file
        count = 0
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            # Skip orma internals and hidden dirs
            rel = f.relative_to(root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if is_ignored(str(rel), patterns):
                continue
            result = backend.on_file_saved(f)
            if result.saved:
                count += 1
        click.echo(f"Tracking {root}")
        click.echo(f"  {count} file(s) scanned and versioned.")

        from orma.config import add_tracked_dir

        add_tracked_dir(str(root))
    finally:
        backend.close()


@main.command()
@click.argument(
    "directory", type=click.Path(exists=True, file_okay=False)
)
def status(directory: str) -> None:
    """Show tracking status for a directory."""
    root = Path(directory).resolve()
    if not (root / ".orma").is_dir():
        click.echo(
            f"Error: {directory} is not tracked.", err=True
        )
        sys.exit(1)

    from orma.db import Ledger

    ledger = Ledger(root)
    ledger.open()
    try:
        files = ledger.get_file_count()
        versions = ledger.get_total_versions()
        click.echo(f"Tracked directory: {root}")
        click.echo(f"  Files:    {files}")
        click.echo(f"  Versions: {versions}")
    finally:
        ledger.close()


@main.command()
@click.argument("filepath", type=click.Path(exists=True))
def history(filepath: str) -> None:
    """Show the version history of a tracked file."""
    path = Path(filepath).resolve()
    root = _find_root(path)
    if root is None:
        click.echo(f"Error: {filepath} is not inside a tracked directory.", err=True)
        sys.exit(1)

    backend = _get_backend(root)
    try:
        versions = backend.get_history(path)
        if not versions:
            click.echo(f"No history found for {filepath}")
            return

        click.echo(f"History for {path.relative_to(root)}  ({len(versions)} versions)")
        click.echo()
        for v in versions:
            ts = v.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            size_kb = v.size_bytes / 1024
            sha_short = v.sha256[:12]
            click.echo(
                f"  v{v.version_number:<4}  {ts}"
                f"  {size_kb:>8.1f} KB  {sha_short}"
            )
    finally:
        backend.close()


@main.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.argument("version", type=int)
def restore(filepath: str, version: int) -> None:
    """Restore a file to a previous version."""
    path = Path(filepath).resolve()
    root = _find_root(path)
    if root is None:
        click.echo(f"Error: {filepath} is not inside a tracked directory.", err=True)
        sys.exit(1)

    backend = _get_backend(root)
    try:
        content = backend.reconstruct_version(path, version)
        path.write_bytes(content)
        click.echo(f"Restored {path.relative_to(root)} to v{version}")
    finally:
        backend.close()


@main.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
def watch(directory: str) -> None:
    """Watch a tracked directory and auto-version file changes."""
    from orma.watcher import DirectoryWatcher

    root = Path(directory).resolve()
    if not (root / ".orma").is_dir():
        click.echo(
            f"Error: {directory} is not tracked."
            " Run `orma track` first.",
            err=True,
        )
        sys.exit(1)

    backend = _get_backend(root)

    def on_change(path: Path) -> None:
        if not path.is_file():
            return
        result = backend.on_file_saved(path)
        if result.saved:
            rel = path.relative_to(root)
            click.echo(f"  v{result.version_number}: {rel}")

    def on_delete(path: Path) -> None:
        rel = str(path.resolve().relative_to(root))
        backend._db.deactivate_file(rel)
        click.echo(f"  deleted: {rel}")

    def on_move(src: Path, dest: Path) -> None:
        old_rel = str(src.resolve().relative_to(root))
        new_rel = str(dest.resolve().relative_to(root))
        backend._db.rename_file(old_rel, new_rel)
        click.echo(f"  moved: {old_rel} -> {new_rel}")
        # Also version the file at its new location
        if dest.is_file():
            on_change(dest)

    watcher = DirectoryWatcher(
        root, on_change,
        on_file_delete=on_delete,
        on_file_move=on_move,
    )

    def shutdown(_sig: int, _frame: object) -> None:
        click.echo("\nStopping watcher...")
        watcher.stop()
        backend.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    click.echo(f"Watching {root} for changes (Ctrl+C to stop)")
    watcher.start()

    # Block the main thread until signaled
    signal.pause()


@main.command()
def daemon() -> None:
    """Run the Orma daemon (watches all tracked directories)."""
    import logging as _logging

    from orma.config import get_tracked_dirs
    from orma.watcher import DirectoryWatcher

    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    tracked = get_tracked_dirs()
    if not tracked:
        click.echo("No tracked directories. Run `orma track` first.")
        sys.exit(0)

    watchers: list[DirectoryWatcher] = []
    backends: list[GitBackend] = []

    for dir_path in tracked:
        root = Path(dir_path)
        if not root.is_dir() or not (root / ".orma").is_dir():
            click.echo(
                f"  skipping {dir_path} (missing or not tracked)",
                err=True,
            )
            continue

        backend = _get_backend(root)
        backends.append(backend)

        def make_on_change(b: GitBackend, r: Path):
            def on_change(path: Path) -> None:
                if not path.is_file():
                    return
                b.on_file_saved(path)
            return on_change

        w = DirectoryWatcher(root, make_on_change(backend, root))
        watchers.append(w)

    if not watchers:
        click.echo("No valid tracked directories found.")
        sys.exit(1)

    def shutdown(_sig: int, _frame: object) -> None:
        for w in watchers:
            w.stop()
        for b in backends:
            b.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    click.echo(f"Orma daemon: watching {len(watchers)} directory(s)")
    for w in watchers:
        w.start()

    signal.pause()
