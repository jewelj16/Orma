# Orma (ഓർമ്മ) — Project Roadmap

**Orma** — Malayalam for *memory*. A local, daemonized file-versioning
system for Ubuntu: it remembers every save of every tracked file without
needing Git as a user-facing concept.

> Alternate names considered: **Smriti** (Sanskrit, "memory/recollection"),
> **Ninaivu** (Tamil, "memory"). Going with **Orma** — short, easy to type
> as a CLI verb (`orma track`), and it doesn't collide with any existing
> well-known tool.

**Strategy, unchanged from the original plan:** ship fast with Git as a
scaffolding backend (Phase n-1), then swap it for a purpose-built
reverse-delta engine (Phase n onward) — without touching the CLI, the
watcher, or the database layer. The swap is possible because every phase
is built around one seam: a single abstract interface both backends
implement.

---

## 0. Naming & Renaming Checklist

Before any new code is written, the existing Phase-0 prototype gets
renamed end to end. This is its own tiny phase because half-renamed
projects are a common source of confusing bugs later.

| Old | New |
|---|---|
| `filevault/` (package) | `orma/` |
| `filevault` (CLI command) | `orma` |
| `FileVersionStore` | `VersionBackend` implementations (see §1) |
| `.filevault/` (metadata dir) | `.orma/` |
| `.versions/` (patch storage dir) | `.orma-versions/` |
| `filevault.service` | `orma.service` |
| `FILEVAULT_DIR` constant | `ORMA_DIR` |

**Commit plan:**
```
chore(rename): rename package filevault/ -> orma/, update imports
chore(rename): rename CLI entry point filevault -> orma in pyproject.toml
chore(rename): rename runtime dirs .filevault/ -> .orma/, .versions/ -> .orma-versions/
chore(rename): rename systemd unit filevault.service -> orma.service
docs(rename): update README references from FileVault to Orma
```

---

## 1. Design Principle Behind the Whole Roadmap

Everything hinges on isolating "how a version is stored and reconstructed"
behind one interface, so replacing the implementation later is a
**single-class swap**, not a rewrite.

```
orma/
├── cli.py              <- never imports git or difflib/bsdiff4 directly
├── watcher.py           <- never imports git or difflib/bsdiff4 directly
├── db.py                 <- ledger schema stays backend-agnostic
└── backends/
    ├── base.py            <- VersionBackend (abstract interface) — THE seam
    ├── git_backend.py      <- Phase n-1 implementation
    └── delta_backend.py     <- Phase n+1 implementation (custom, from scratch)
```

```python
class VersionBackend(ABC):
    @abstractmethod
    def init_tracking(self, root_dir: Path) -> None: ...

    @abstractmethod
    def on_file_saved(self, path: Path) -> SaveResult: ...

    @abstractmethod
    def get_history(self, path: Path) -> list[VersionInfo]: ...

    @abstractmethod
    def reconstruct_version(self, path: Path, version_number: int) -> bytes: ...
```

`cli.py`, `watcher.py`, and `db.py` are written once against this interface
and are **never modified again** for the rest of the roadmap except for
additive, non-breaking changes explicitly called out per phase. Only the
file inside `backends/` changes for storage-engine work. This is the
mechanism that makes "remove git, replace with a custom algorithm, touch
nothing else" actually true rather than aspirational.

---

## 2. Complete Work Plan, Start to End

One flat table of every task across the whole project, in build order,
so you can see the full shape before diving into any one phase's detail.
"Effort" is rough sizing (S = <1 day, M = 1-3 days, L = 3-7 days), not a
commitment.

| # | Phase | Task | Effort | Depends on |
|---|---|---|---|---|
| 1 | 0 | Rename `filevault` → `orma` across package, CLI, dirs, systemd unit | S | — |
| 2 | n-1 | Design & write `VersionBackend` ABC + shared value objects | S | 1 |
| 3 | n-1 | Refactor `cli.py` to depend only on `VersionBackend` | S | 2 |
| 4 | n-1 | Refactor `watcher.py` to depend only on `VersionBackend` | S | 2 |
| 5 | n-1 | Implement `GitBackend.init_tracking` (hidden git-dir setup) | M | 2 |
| 6 | n-1 | Implement `GitBackend.on_file_saved` (add/commit + ledger mirror) | M | 5 |
| 7 | n-1 | Implement `GitBackend.get_history` / `reconstruct_version` | M | 5 |
| 8 | n-1 | Wire `orma track/history/restore` end to end against `GitBackend` | M | 3,4,5,6,7 |
| 9 | n-1 | Split `track` into daemon entrypoint; finish `orma.service` | M | 8 |
| 10 | n-1 | `.ormaignore` support | S | 8 |
| 11 | n-1 | Handle renames/deletes/moves as first-class events | M | 8 |
| 12 | n-1 | Edge cases: symlinks, dir-replaces-file, large files, permissions | M | 8 |
| 13 | n-1 | **Ship v1.0** (tag, changelog, README pass) | S | 6-12 |
| 14 | n | Write backend-conformance test suite (spec, no implementation) | M | 13 |
| 15 | n | Run conformance suite against `GitBackend`; fix any gaps it exposes | S | 14 |
| 16 | n | Finalize `DeltaBackend` design doc (diff algo table, compaction plan) | S | 15 |
| 17 | n+1 | Promote Phase-0 prototype logic into `backends/delta_backend.py` | M | 16 |
| 18 | n+1 | Add SHA-256 integrity assertion on every reconstruction | S | 17 |
| 19 | n+1 | Run conformance suite against `DeltaBackend` until green | M | 17,18 |
| 20 | n+2 | Add `backend: git \| delta` per-directory config flag | S | 19 |
| 21 | n+2 | Implement `--shadow` dual-write + mismatch logging | M | 20 |
| 22 | n+2 | Burn-in period on real (low-stakes) directories | L | 21 |
| 23 | n+3 | Build `orma migrate-backend` (replay git log through `DeltaBackend`) | M | 22 |
| 24 | n+3 | Flip default backend to `delta` for new `orma track` calls | S | 22 |
| 25 | n+3 | Delete `git_backend.py` + git dependency once migration verified | S | 23,24 |
| 26 | n+3 | **Ship v2.0** (Git fully removed) | S | 25 |
| 27 | n+4 | Reserve/activate `is_base_snapshot` compaction flag in schema | S | 26 |
| 28 | n+4 | Implement compaction logic + `orma gc` command | M | 27 |
| 29 | n+4 | Retention policy config (age/count based pruning) | S | 28 |
| 30 | n+5 | Atomic multi-file save grouping | L | 26 |
| 31 | n+5 | Encryption at rest for `.orma-versions/` | L | 26 |
| 32 | n+5 | `orma ui` (TUI/web history browser) | L | 26 |
| 33 | n+5 | Remote sync backend (`backends/remote_backend.py`) | L | 26 |
| 34 | n+5 | Content-addressed dedup across machines | L | 33 |
| 35 | n+5 | Editor integrations (VS Code / vim) | M | 32 |

---

## 3. Phase 0 — Foundation *(status: done, pending rename)*

- [x] Project scaffolding (`orma/`, `systemd/`, `pyproject.toml`)
- [x] SQLite ledger schema (`files`, `versions` tables) in `db.py`
- [x] `watchdog`-based debounced save-event watcher (`watcher.py`)
- [x] CLI skeleton: `track`, `history`, `restore` (`cli.py`)
- [x] First working reverse-delta storage engine (proof of concept) —
      proved the concept (difflib for text, bsdiff4 for binary, zlib
      compression), tested round-trip correct across text/binary/fallback
      cases
- [ ] Rename pass (§0 above)

**Commit plan:**
```
chore: initial project scaffolding (package layout, pyproject.toml)
feat(db): add SQLite ledger schema (files, versions tables)
feat(storage): implement reverse-delta save handler (proof of concept)
feat(storage): add difflib text-patch compute/apply
feat(storage): add bsdiff4 binary patch support with full-snapshot fallback
test(storage): verify text/binary/fallback round-trip correctness
feat(watcher): add debounced watchdog event handler
feat(cli): add track/history/restore command skeleton
docs: initial README with architecture and schema
chore(rename): rename filevault -> orma across package, CLI, dirs, systemd unit
```

---

## 4. Phase n-1 — Complete the Project with Git

**Goal:** ship a fully working, end-to-end product as fast as possible by
letting Git do the hard part (diffing, storage, integrity) while Orma
handles watching, the CLI, and presentation. This de-risks everything
*except* storage before investing in a custom storage engine.

### n-1.1 — Define the backend interface

- `backends/base.py`: `VersionBackend` ABC (see §1).
- Shared value objects: `SaveResult`, `VersionInfo` (version number,
  timestamp, size, and a backend-opaque `ref` field — a commit hash for
  Git, a patch path for Delta — so `history`/`restore` never need to know
  which backend produced it).
- Refactor `cli.py` and `watcher.py` to depend only on `VersionBackend`.

**Commit plan:**
```
feat(backends): add VersionBackend abstract interface
feat(backends): add SaveResult and VersionInfo value objects
refactor(cli): depend on VersionBackend interface instead of concrete storage
refactor(watcher): depend on VersionBackend interface instead of concrete storage
test(backends): add interface contract test stubs (no impl yet)
```

### n-1.2 — Implement `GitBackend`

- Each tracked root gets its own git repo: hidden git-dir
  (`<root>/.orma/repo.git`) with `<root>` as the working tree
  (`git --git-dir=... --work-tree=...`), so the user's directory never
  shows a visible `.git`.
- `on_file_saved(path)`: `git add` → `git commit` (empty-commit guard on
  unchanged hash, mirroring the no-op behavior from Phase 0) → mirror
  commit metadata into the *same* `files`/`versions` tables (`patch_type
  = 'git_commit'`, commit hash stored in `versions.patch_path`) so
  `history`/`restore` don't need backend-specific branches downstream.
- `get_history(path)`: `git log --follow -- <path>`.
- `reconstruct_version(path, n)`: `git show <commit>:<relpath>`.

**Commit plan:**
```
feat(backends/git): implement init_tracking (hidden git-dir setup)
feat(backends/git): implement on_file_saved (add/commit + ledger mirror)
feat(backends/git): implement get_history via git log --follow
feat(backends/git): implement reconstruct_version via git show
test(backends/git): round-trip test across text and binary files
fix(backends/git): guard against empty commits on no-op saves
```

### n-1.3 — Wire it all together

**Commit plan:**
```
feat(cli): wire track command to GitBackend.init_tracking + initial scan
feat(cli): wire history command to GitBackend.get_history
feat(cli): wire restore command to GitBackend.reconstruct_version
test(cli): end-to-end test — track, edit, history, restore
```

### n-1.4 — Daemonize

**Commit plan:**
```
refactor(cli): split track into "register + scan" and daemon hand-off
feat(daemon): add orma-daemon long-running entrypoint for systemd
feat(systemd): finalize orma.service unit (Restart=on-failure, logging)
docs(systemd): document install/enable/status/journalctl steps
test(daemon): verify daemon restart-on-crash and survives logout/login
```

### n-1.5 — Harden & ship v1.0

**Commit plan:**
```
feat(watcher): add .ormaignore glob support
feat(watcher): handle file renames and moves as first-class events
feat(watcher): handle file deletions (tombstone in ledger, not a version)
fix(watcher): handle symlinks, dir-replaces-file, permission-denied files
feat(storage): add large-file size cap with warning
docs: full README pass for v1.0
chore(release): tag v1.0.0 — Git-backed Orma
```

**Deliverable:** Orma v1.0 — fully functional daemon, CLI, and systemd
service, using Git as the storage backend under the hood.

### Why this phase matters even though Git gets removed later

It validates the *entire rest of the system* — event handling, debounce
correctness, CLI UX, daemon lifecycle, ledger schema shape — against a
backend that is known-correct. Any bug found after n-1 is a storage-engine
bug, not an architecture bug, which makes Phase n much easier to trust.

---

## 5. Phase n — Design the Custom Version-Control Algorithm

**Goal:** specify, on paper, the from-scratch reverse-delta engine that
will replace Git — *before* writing the replacement class. No code changes
to anything outside `backends/` happen in this phase.

### n.1 — Formalize the storage model

- Confirm the reverse-delta model: tracked directory always holds the
  latest complete file; `.orma-versions/<relpath>/` holds `snapshot.z`
  (diff base) + `patches/vN.patch.z` (patch that rebuilds version N from
  version N+1).
- Reserve an `is_base_snapshot` boolean on the `versions` table now, even
  though it's unused until Phase n+4's compaction — avoids a breaking
  schema migration later.

### n.2 — Diff/patch algorithm selection (per file type)

| File type | Algorithm | Rationale |
|---|---|---|
| Text | `difflib.SequenceMatcher` opcodes, JSON-serialized | No native deps, human-auditable patches, good ratio on line-based edits |
| Binary | `bsdiff4` | Purpose-built for exactly this reconstruct-A-from-B use case |
| Anything where the "smart" patch loses to a raw copy | Full zlib snapshot | Correctness floor — never worse than storing the whole file |

### n.3 — Compression & integrity

- zlib level 9 on every patch and snapshot.
- SHA-256 on every version — used to detect no-op saves *and*, newly in
  this phase, to verify reconstruction integrity: `reconstruct_version`
  must assert its output hash matches the stored hash before returning.

### n.4 — Write the backend-conformance test suite *before* the implementation

- A backend-agnostic suite that runs against **any** `VersionBackend`:
  save N versions, assert `get_history` returns N entries, assert
  `reconstruct_version(i)` matches what was saved at step i for every i.
- Run it against `GitBackend` first — it should already pass. This is
  what makes the eventual swap verifiable rather than "seems fine."

**Commit plan:**
```
docs(design): formalize reverse-delta storage model + compaction hooks
docs(schema): add is_base_snapshot column (unused until Phase n+4)
docs(design): diff/patch algorithm selection table
test(backends): add backend-agnostic conformance suite
test(backends/git): confirm GitBackend passes conformance suite
```

**Deliverable:** design doc (this section) + a backend conformance test
suite with zero implementation of `DeltaBackend` yet.

---

## 6. Phase n+1 — Implement `DeltaBackend` (the custom engine)

- Promote Phase 0's prototype logic into `backends/delta_backend.py`,
  conforming to the `VersionBackend` ABC.
- Add the integrity assertion from n.3 (hash-check every reconstruction).
- Run the n.4 conformance suite against `DeltaBackend` until it passes
  identically to `GitBackend`.
- **No changes to `cli.py`, `watcher.py`, or `db.py` in this phase** — if
  any change is needed there, the Phase n-1.1 interface was
  under-specified, and the interface should be fixed, not bypassed.

**Commit plan:**
```
feat(backends/delta): scaffold DeltaBackend implementing VersionBackend
feat(backends/delta): implement init_tracking + first-save snapshot logic
feat(backends/delta): implement on_file_saved (hash/diff/compress/ledger)
feat(backends/delta): implement text patch compute/apply (difflib, JSON)
feat(backends/delta): implement binary patch via bsdiff4 with fallback
feat(backends/delta): implement reconstruct_version (backwards patch walk)
feat(backends/delta): add SHA-256 verification on every reconstruction
test(backends/delta): run conformance suite — text, binary, fallback cases
test(backends/delta): large-file and long-chain stress test
```

---

## 7. Phase n+2 — Shadow Mode (validate before cutting over)

De-risk the swap by running both backends side by side before removing Git.

- `backend: git | delta` config flag, settable per tracked directory.
- `--shadow` mode: every save runs through **both** backends;
  `DeltaBackend`'s reconstructions are diffed against `GitBackend`'s for
  every version, with mismatches logged loudly (not silently swallowed).
- Dogfood on real, low-stakes directories for a defined burn-in period
  (e.g. two weeks of real editing activity) before trusting it on
  anything that matters.

**Commit plan:**
```
feat(config): add per-directory backend selection (git | delta)
feat(daemon): implement --shadow dual-write mode
feat(daemon): add mismatch detection + loud logging between backends
chore(ops): dogfood shadow mode on real low-stakes directories
docs(shadow): document burn-in exit criteria and how to read mismatch logs
```

**Exit criterion:** zero reconstruction mismatches across the burn-in
period, across both text and binary files, across normal editing patterns
(rapid saves, large files, renames).

---

## 8. Phase n+3 — Cut Over: Remove Git

- Flip the default `backend` to `delta` for new `orma track` calls.
- `orma migrate-backend`: for directories currently on `GitBackend`, walk
  the git log and replay each historical commit through
  `DeltaBackend.on_file_saved()` in order, preserving history instead of
  resetting to v1.
- Delete `backends/git_backend.py` and the git dependency from
  `pyproject.toml` once migration is confirmed working and no tracked
  directory still depends on it.

**Commit plan:**
```
feat(cli): add orma migrate-backend command (replay git log -> delta)
test(migrate): verify migrated history matches pre-migration reconstructions
feat(config): flip default backend to delta for new track calls
chore(deps): remove GitPython/git subprocess dependency
chore(cleanup): delete backends/git_backend.py
docs: update README — Orma is now fully Git-free
chore(release): tag v2.0.0 — Git-free Orma
```

**Deliverable:** Orma v2.0 — Git fully removed, running entirely on the
from-scratch reverse-delta engine. `cli.py`, `watcher.py`, `db.py` are, by
construction, unchanged from v1.0.

---

## 9. Phase n+4 — Compaction & Long-Term Storage Health

Long-lived files accumulate long patch chains, which makes restoring an
old version slower (more patches to walk) and directories heavier.

- Base-snapshot compaction: every K versions (configurable), write a
  fresh full snapshot as a new chain root instead of another patch, so
  `reconstruct_version` never has to walk more than K patches.
- `orma gc <dir>`: manual trigger for compaction + pruning of versions
  older than a retention policy (age-based or count-based).
- Uses the `is_base_snapshot` flag reserved back in Phase n.1 — no schema
  migration needed.

**Commit plan:**
```
feat(backends/delta): activate is_base_snapshot for compaction chain roots
feat(backends/delta): implement periodic compaction logic (every K versions)
feat(cli): add orma gc command (manual compaction + pruning trigger)
feat(config): add retention policy settings (age/count based)
test(compaction): verify old-version reconstruction still correct post-compaction
```

---

## 10. Phase n+5 and Beyond — Extensions

Roughly in priority order, each isolated behind `VersionBackend` or
additive to the CLI/daemon without touching the storage core.

| Extension | Commit plan sketch |
|---|---|
| Atomic multi-file save grouping | `feat(watcher): detect burst-save windows`, `feat(db): add save_group_id column`, `feat(cli): show grouped saves in history` |
| Encryption at rest | `feat(backends/delta): encrypt patches/snapshots at rest`, `feat(cli): add orma unlock for key prompt`, `docs(security): key management guide` |
| `orma ui` (TUI/web browser) | `feat(ui): scaffold TUI reading VersionBackend.get_history`, `feat(ui): add version diff view`, `feat(ui): add restore-from-ui action` |
| Remote sync backend | `feat(backends/remote): scaffold RemoteBackend implementing VersionBackend`, `feat(backends/remote): implement S3/SFTP mirroring of .orma-versions/`, `test(backends/remote): conformance suite pass` |
| Content-addressed dedup | `feat(storage): key patches by SHA-256 content address`, `feat(storage): cross-directory dedup of identical patches` |
| Editor integrations | `feat(integrations/vscode): call orma history/restore from command palette`, `feat(integrations/vim): plugin wrapping orma CLI` |

---

## 11. Summary Table

| Phase | Storage backend | What changes | What stays frozen |
|---|---|---|---|
| 0 | proof-of-concept delta engine | everything (initial build) + rename to Orma | — |
| n-1 | **Git** | `backends/git_backend.py`, daemon/systemd, CLI hardening | ledger schema shape, CLI command surface |
| n | *(design only, no backend change)* | design doc + conformance test suite | everything shipped in n-1 |
| n+1 | Git (unchanged) + **new** `DeltaBackend` built alongside | `backends/delta_backend.py` only | `cli.py`, `watcher.py`, `db.py` |
| n+2 | Git (default) / Delta (shadow) | config flag, shadow-mode runner | `cli.py`, `watcher.py`, `db.py`, both backend files |
| n+3 | **Delta (default)**, Git removed | delete `git_backend.py` + git dependency, add migration tool | `cli.py`, `watcher.py`, `db.py` |
| n+4 | Delta + compaction | compaction logic inside `delta_backend.py` | everything else |
| n+5+ | Delta (+ optional remote) | new backend files, new CLI subcommands | core interface contract |
