# Orma (ഓർമ്മ)

**Orma** — Malayalam for *memory*. A local, daemonized file-versioning system
for Ubuntu that remembers every save of every tracked file, without requiring
Git as a user-facing concept.

## Features

- **Automatic versioning** — every file save creates a new version
- **No-op detection** — unchanged saves are skipped (SHA-256 comparison)
- **Debounced watching** — rapid saves coalesce into a single version
- **`.ormaignore`** — skip files by glob pattern (`.gitignore`-style syntax)
- **Rename/delete tracking** — moves update the ledger, deletes soft-deactivate
- **Edge-case hardening** — symlinks skipped, large files capped, permission errors handled
- **Daemon mode** — `orma daemon` watches all tracked directories (systemd-ready)
- **Instant history & restore** — browse versions and restore any previous state

## Quick Start

```bash
# Install (editable, for development)
pip install -e ".[dev]"

# Track a directory
orma track ~/projects/my-code

# Check status
orma status ~/projects/my-code

# View file history
orma history ~/projects/my-code/main.py

# Restore a previous version
orma restore ~/projects/my-code/main.py 3

# Watch for live changes (single directory)
orma watch ~/projects/my-code

# Run the daemon (watches all tracked directories)
orma daemon
```

## CLI Commands

| Command | Description |
|---|---|
| `orma track <dir>` | Initialize tracking + scan existing files |
| `orma status <dir>` | Show file count and version count |
| `orma history <file>` | Show version history (newest first) |
| `orma restore <file> <N>` | Restore file to version N |
| `orma watch <dir>` | Watch a single directory for changes |
| `orma daemon` | Watch all tracked directories (for systemd) |
| `orma --version` | Show version |

## Architecture

```
orma/
├── __init__.py          # package root (version)
├── cli.py               # Click CLI — all user-facing commands
├── config.py            # persistent tracked-directory registry
├── db.py                # SQLite ledger (files + versions tables)
├── ignore.py            # .ormaignore glob pattern matching
├── watcher.py           # debounced watchdog event handler
└── backends/
    ├── base.py           # VersionBackend ABC — the central abstraction seam
    └── git_backend.py    # Git-backed storage (hidden git-dir)
```

**Key design principle:** everything outside `backends/` codes against the
`VersionBackend` interface.  Swapping the storage engine (e.g., Git → custom
delta) is a single-class change — `cli.py`, `watcher.py`, and `db.py` never
need to know which backend is active.

### Storage Model (Git Backend)

Each tracked directory gets a hidden Git repository at `<dir>/.orma/repo.git`
with the tracked directory as the working tree.  Files are never exposed to
a user-visible `.git`.  Each save becomes `git add + git commit`, with
metadata mirrored into a SQLite ledger for fast queries.

### Ledger Schema

**files** — one row per tracked file (keyed by root-relative path)

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment ID |
| `rel_path` | TEXT UNIQUE | Path relative to tracked root |
| `first_tracked` | TEXT | ISO-8601 UTC timestamp |
| `is_active` | INTEGER | 1 = active, 0 = soft-deleted |

**versions** — one row per saved version

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment ID |
| `file_id` | INTEGER FK | References files(id) |
| `version_number` | INTEGER | 1-based version ordinal |
| `timestamp` | TEXT | ISO-8601 UTC |
| `size_bytes` | INTEGER | File size at this version |
| `sha256` | TEXT | Content hash |
| `patch_type` | TEXT | e.g. `git_commit` |
| `ref` | TEXT | Backend-opaque reference |
| `is_base_snapshot` | INTEGER | Reserved for future compaction |

## .ormaignore

Create a `.ormaignore` file in your tracked directory to skip files:

```
# Build artifacts
*.pyc
__pycache__
dist/
*.egg-info

# Large generated files
*.bin
*.so
```

Syntax: one glob per line, `#` for comments, blank lines ignored. Patterns
match against the full relative path, basename, and directory components.

## Systemd (User Service)

```bash
# Install the unit
mkdir -p ~/.config/systemd/user/
cp systemd/orma.service ~/.config/systemd/user/

# Enable and start
systemctl --user daemon-reload
systemctl --user enable orma
systemctl --user start orma

# Check status
systemctl --user status orma

# View logs
journalctl --user -u orma -f
```

## Development

```bash
# Create a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check orma/ tests/
```

## Roadmap

See [orma_roadmap.md](orma_roadmap.md) for the full project roadmap,
including the planned custom reverse-delta engine that will replace Git.

## License

MIT — see [LICENSE](LICENSE).
