"""Orma config — persistent configuration and tracked-directory registry.

Stores a JSON config at ``~/.config/orma/config.json`` containing
the list of directories being tracked.  The daemon reads this on
startup to know which directories to watch.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "orma"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load() -> dict:
    """Load config from disk, or return defaults."""
    if CONFIG_FILE.is_file():
        return json.loads(CONFIG_FILE.read_text())
    return {"tracked_dirs": []}


def _save(config: dict) -> None:
    """Write config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def get_tracked_dirs() -> list[str]:
    """Return the list of tracked directory paths."""
    return _load().get("tracked_dirs", [])


def add_tracked_dir(directory: str) -> None:
    """Register a directory as tracked (idempotent)."""
    config = _load()
    dirs = config.get("tracked_dirs", [])
    abspath = str(Path(directory).resolve())
    if abspath not in dirs:
        dirs.append(abspath)
        config["tracked_dirs"] = dirs
        _save(config)
        logger.info("registered tracked dir: %s", abspath)


def remove_tracked_dir(directory: str) -> None:
    """Unregister a tracked directory."""
    config = _load()
    dirs = config.get("tracked_dirs", [])
    abspath = str(Path(directory).resolve())
    if abspath in dirs:
        dirs.remove(abspath)
        config["tracked_dirs"] = dirs
        _save(config)
