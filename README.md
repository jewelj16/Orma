# Orma (ഓർമ്മ)

**Orma** — Malayalam for *memory*. A local, daemonized file-versioning system
for Ubuntu: it remembers every save of every tracked file without needing Git
as a user-facing concept.

## Quick Start

```bash
# Install (editable, for development)
pip install -e ".[dev]"

# Track a directory
orma track ~/projects/my-code

# View file history
orma history ~/projects/my-code/main.py

# Restore a previous version
orma restore ~/projects/my-code/main.py 3
```

## Architecture

```
orma/
├── cli.py               ← user-facing commands (track, history, restore)
├── watcher.py           ← debounced filesystem event handler (watchdog)
├── db.py                ← SQLite ledger (files + versions tables)
└── backends/
    ├── base.py           ← VersionBackend ABC — the central abstraction seam
    ├── git_backend.py    ← Phase n-1: Git-backed storage (ships first)
    └── delta_backend.py  ← Phase n+1: custom reverse-delta engine (replaces Git)
```

Everything outside `backends/` codes against the `VersionBackend` interface.
Swapping the storage engine is a single-class change — `cli.py`, `watcher.py`,
and `db.py` never need to know which backend is active.

## Development

```bash
# Create a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check orma/ tests/
```

## Systemd (User Service)

```bash
# Install the unit
mkdir -p ~/.config/systemd/user/
cp systemd/orma.service ~/.config/systemd/user/

# Enable and start
systemctl --user enable orma
systemctl --user start orma

# Check logs
journalctl --user -u orma -f
```

## License

MIT
