"""Multi-database registry with JSON persistence and thread-safe access."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

STATE_FILE = os.environ.get("PG_MCP_STATE_FILE", "/data/db_state.json")


@dataclass
class DatabaseInfo:
    name: str
    uri: str
    access_mode: str = "unrestricted"
    connected: bool = False
    pool_min: int = 2
    pool_max: int = 10

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("connected", None)
        return d

    def safe_uri(self) -> str:
        """Return URI with password redacted for logging."""
        import re
        return re.sub(r"(://[^:@/]+:)[^@]+(@)", r"\1****\2", self.uri)


class DatabaseRegistry:
    def __init__(self) -> None:
        self._databases: dict[str, DatabaseInfo] = {}
        self._active: str = ""
        self._lock = threading.Lock()

    @property
    def active(self) -> str:
        with self._lock:
            return self._active

    @active.setter
    def active(self, name: str) -> None:
        with self._lock:
            self._active = name

    def add(self, db: DatabaseInfo) -> None:
        with self._lock:
            self._databases[db.name] = db
            if not self._active:
                self._active = db.name
        self.save()

    def remove(self, name: str) -> DatabaseInfo | None:
        with self._lock:
            db = self._databases.pop(name, None)
            if db and self._active == name:
                self._active = next(iter(self._databases), "")
        if db:
            self.save()
        return db

    def get(self, name: str) -> DatabaseInfo | None:
        with self._lock:
            return self._databases.get(name)

    def list_all(self) -> list[DatabaseInfo]:
        with self._lock:
            return list(self._databases.values())

    def save(self) -> None:
        with self._lock:
            state = {
                "active": self._active,
                "databases": [db.to_dict() for db in self._databases.values()],
            }
        try:
            path = Path(STATE_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        except Exception:
            log.exception("Failed to save state to %s", STATE_FILE)

    def load(self) -> list[dict]:
        try:
            path = Path(STATE_FILE)
            if path.exists():
                state = json.loads(path.read_text())
                with self._lock:
                    self._active = state.get("active", "")
                    dbs = state.get("databases", [])
                    for d in dbs:
                        self._databases[d["name"]] = DatabaseInfo(**d)
                log.info("Loaded %d databases from state", len(dbs))
                return dbs
        except Exception:
            log.exception("Failed to load state from %s", STATE_FILE)
        return []


registry = DatabaseRegistry()
