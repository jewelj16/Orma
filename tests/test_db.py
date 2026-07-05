"""Tests for the SQLite ledger (orma.db)."""

from pathlib import Path

from orma.db import Ledger


def test_ledger_creates_database(tmp_path: Path) -> None:
    """Opening a ledger in a fresh directory creates .orma/ledger.db."""
    ledger = Ledger(tmp_path)
    ledger.open()
    try:
        assert (tmp_path / ".orma" / "ledger.db").exists()
    finally:
        ledger.close()


def test_ensure_file_inserts_and_deduplicates(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    ledger.open()
    try:
        fid1 = ledger.ensure_file("src/main.py")
        fid2 = ledger.ensure_file("src/main.py")
        fid3 = ledger.ensure_file("README.md")
        assert fid1 == fid2  # idempotent
        assert fid1 != fid3  # different file gets different id
    finally:
        ledger.close()


def test_add_and_retrieve_versions(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    ledger.open()
    try:
        fid = ledger.ensure_file("hello.txt")

        assert ledger.get_latest_version_number(fid) == 0
        assert ledger.get_latest_sha256(fid) is None

        ledger.add_version(fid, 1, 100, "aaa", "full_snapshot", "/v1")
        ledger.add_version(fid, 2, 120, "bbb", "text_delta", "/v2")

        assert ledger.get_latest_version_number(fid) == 2
        assert ledger.get_latest_sha256(fid) == "bbb"

        rows = ledger.get_versions(fid)
        assert len(rows) == 2
        assert rows[0][0] == 2  # newest first
        assert rows[1][0] == 1
    finally:
        ledger.close()


def test_get_file_id_returns_none_for_unknown(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    ledger.open()
    try:
        assert ledger.get_file_id("nonexistent.txt") is None
    finally:
        ledger.close()
