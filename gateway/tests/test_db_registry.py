"""Tests for gateway.db_registry — DatabaseInfo, DatabaseRegistry."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from unittest.mock import patch


class TestDatabaseInfo:
    """Tests for DatabaseInfo dataclass."""

    def test_defaults(self):
        from gateway.db_registry import DatabaseInfo
        db = DatabaseInfo(name="mydb", uri="postgresql://localhost/mydb")
        assert db.name == "mydb"
        assert db.uri == "postgresql://localhost/mydb"
        assert db.access_mode == "unrestricted"
        assert db.connected is False
        assert db.pool_min == 2
        assert db.pool_max == 10

    def test_custom_values(self):
        from gateway.db_registry import DatabaseInfo
        db = DatabaseInfo(
            name="analytics",
            uri="postgresql://localhost/analytics",
            access_mode="restricted",
            connected=True,
            pool_min=5,
            pool_max=20,
        )
        assert db.access_mode == "restricted"
        assert db.connected is True
        assert db.pool_min == 5
        assert db.pool_max == 20

    def test_to_dict_excludes_connected(self):
        from gateway.db_registry import DatabaseInfo
        db = DatabaseInfo(name="mydb", uri="postgresql://localhost/mydb", connected=True)
        d = db.to_dict()
        assert "connected" not in d
        assert d["name"] == "mydb"
        assert d["uri"] == "postgresql://localhost/mydb"
        assert d["access_mode"] == "unrestricted"
        assert d["pool_min"] == 2
        assert d["pool_max"] == 10


class TestDatabaseRegistry:
    """Tests for DatabaseRegistry operations."""

    def _make_registry(self, tmp_path: str):
        """Create a fresh registry with a temp state file."""
        from gateway.db_registry import DatabaseRegistry
        reg = DatabaseRegistry()
        # Override STATE_FILE via env patch
        return reg

    def test_initial_state(self):
        from gateway.db_registry import DatabaseRegistry
        reg = DatabaseRegistry()
        assert reg.list_all() == []
        assert reg.active == ""

    def test_add_first_db_becomes_active(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo
        reg = DatabaseRegistry()

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            db = DatabaseInfo(name="primary", uri="postgresql://localhost/primary")
            reg.add(db)

        assert reg.active == "primary"
        assert reg.get("primary") is db

    def test_add_second_db_does_not_change_active(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            db1 = DatabaseInfo(name="primary", uri="postgresql://localhost/primary")
            db2 = DatabaseInfo(name="secondary", uri="postgresql://localhost/secondary")
            reg.add(db1)
            reg.add(db2)

        assert reg.active == "primary"

    def test_add_multiple_listed(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            reg.add(DatabaseInfo(name="a", uri="postgresql://localhost/a"))
            reg.add(DatabaseInfo(name="b", uri="postgresql://localhost/b"))

        names = {db.name for db in reg.list_all()}
        assert names == {"a", "b"}

    def test_get_nonexistent_returns_none(self):
        from gateway.db_registry import DatabaseRegistry
        reg = DatabaseRegistry()
        assert reg.get("nonexistent") is None

    def test_remove_existing(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            db = DatabaseInfo(name="mydb", uri="postgresql://localhost/mydb")
            reg.add(db)
            removed = reg.remove("mydb")

        assert removed is db
        assert reg.get("mydb") is None

    def test_remove_active_switches_to_next(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            reg.add(DatabaseInfo(name="a", uri="postgresql://localhost/a"))
            reg.add(DatabaseInfo(name="b", uri="postgresql://localhost/b"))
            reg.remove("a")

        assert reg.active == "b"

    def test_remove_nonexistent_returns_none(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            result = reg.remove("nonexistent")

        assert result is None

    def test_remove_last_db_active_becomes_empty(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            reg.add(DatabaseInfo(name="only", uri="postgresql://localhost/only"))
            reg.remove("only")

        assert reg.active == ""

    def test_active_setter(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "state.json")):
            reg.add(DatabaseInfo(name="a", uri="postgresql://localhost/a"))
            reg.add(DatabaseInfo(name="b", uri="postgresql://localhost/b"))

        reg.active = "b"
        assert reg.active == "b"


class TestDatabaseRegistryPersistence:
    """Tests for save/load state file."""

    def test_save_creates_file(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        state_file = str(tmp_path / "state.json")
        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            reg.add(DatabaseInfo(name="mydb", uri="postgresql://localhost/mydb"))

        assert Path(state_file).exists()

    def test_save_correct_json_structure(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        state_file = str(tmp_path / "state.json")
        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            reg.add(DatabaseInfo(name="mydb", uri="postgresql://localhost/mydb"))

        data = json.loads(Path(state_file).read_text())
        assert data["active"] == "mydb"
        assert len(data["databases"]) == 1
        assert data["databases"][0]["name"] == "mydb"
        assert "connected" not in data["databases"][0]

    def test_load_restores_databases(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        state_file = str(tmp_path / "state.json")

        # Save with one registry
        reg1 = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            reg1.add(DatabaseInfo(name="restored", uri="postgresql://localhost/restored"))

        # Load with another registry
        reg2 = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            reg2.load()

        assert reg2.get("restored") is not None
        assert reg2.active == "restored"

    def test_load_nonexistent_file_returns_empty(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry

        state_file = str(tmp_path / "nonexistent.json")
        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            result = reg.load()

        assert result == []

    def test_load_corrupted_file_returns_empty(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry

        state_file = str(tmp_path / "state.json")
        Path(state_file).write_text("not valid json{{{")

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            result = reg.load()

        assert result == []

    def test_save_failure_does_not_raise(self, tmp_path):
        """Save failure (e.g. permission denied) should be swallowed."""
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        # Use a path where directory creation would fail (file as parent)
        bad_file = str(tmp_path / "not_a_dir" / "state.json")
        Path(tmp_path / "not_a_dir").write_text("I am a file, not a dir")

        reg = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", bad_file):
            # Should not raise despite the invalid path
            reg.add(DatabaseInfo(name="x", uri="postgresql://localhost/x"))

    def test_multiple_databases_saved_and_loaded(self, tmp_path):
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        state_file = str(tmp_path / "state.json")
        reg1 = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            reg1.add(DatabaseInfo(name="db1", uri="postgresql://localhost/db1"))
            reg1.add(DatabaseInfo(name="db2", uri="postgresql://localhost/db2",
                                  access_mode="restricted"))

        reg2 = DatabaseRegistry()
        with patch("gateway.db_registry.STATE_FILE", state_file):
            reg2.load()

        assert {db.name for db in reg2.list_all()} == {"db1", "db2"}
        db2 = reg2.get("db2")
        assert db2.access_mode == "restricted"
