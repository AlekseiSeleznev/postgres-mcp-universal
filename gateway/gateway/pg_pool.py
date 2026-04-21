"""asyncpg pool manager — multi-database connection pools with per-session routing."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

import asyncpg

from gateway.config import settings
from gateway.db_registry import DatabaseInfo, registry

log = logging.getLogger(__name__)


@dataclass
class SessionState:
    db_name: str
    last_access: float = field(default_factory=time.time)


class PoolManager:
    def __init__(self) -> None:
        self._pools: dict[str, asyncpg.Pool] = {}
        self._sessions: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._state_lock = threading.RLock()

    # --- Pool lifecycle ---

    async def connect(self, db: DatabaseInfo) -> None:
        async with self._lock:
            with self._state_lock:
                exists = db.name in self._pools
            if exists:
                log.info("Pool %s already exists, skipping", db.name)
                return

        log.info("Creating pool for %s", db.safe_uri())
        pool = await asyncpg.create_pool(
            db.uri,
            min_size=db.pool_min,
            max_size=db.pool_max,
            command_timeout=settings.query_timeout,
        )
        async with self._lock:
            with self._state_lock:
                self._pools[db.name] = pool
        db.connected = True
        log.info("Pool %s connected (%d-%d)", db.name, db.pool_min, db.pool_max)

    async def disconnect(self, name: str) -> None:
        async with self._lock:
            with self._state_lock:
                pool = self._pools.pop(name, None)
                # Clean sessions pointing to this DB
                to_remove = [sid for sid, s in self._sessions.items() if s.db_name == name]
                for sid in to_remove:
                    del self._sessions[sid]

        if pool:
            await pool.close()
            db = registry.get(name)
            if db:
                db.connected = False
            log.info("Pool %s closed", name)

    async def close_all(self) -> None:
        with self._state_lock:
            names = list(self._pools)
        for name in names:
            await self.disconnect(name)

    # --- Session routing ---

    def get_active_db(self, session_id: str | None = None) -> str:
        with self._state_lock:
            if session_id and session_id in self._sessions:
                state = self._sessions[session_id]
                state.last_access = time.time()
                return state.db_name
            return registry.active

    def switch_db(self, db_name: str, session_id: str | None = None) -> None:
        with self._state_lock:
            if db_name not in self._pools:
                raise ValueError(f"Database '{db_name}' is not connected")
            if session_id:
                self._sessions[session_id] = SessionState(db_name=db_name)
            else:
                registry.active = db_name

    def get_pool(self, session_id: str | None = None) -> asyncpg.Pool:
        with self._state_lock:
            if session_id and session_id in self._sessions:
                state = self._sessions[session_id]
                state.last_access = time.time()
                db_name = state.db_name
            else:
                db_name = registry.active

            if not db_name:
                raise RuntimeError("No active database. Use connect_database first.")
            pool = self._pools.get(db_name)
            if not pool:
                raise RuntimeError(f"Database '{db_name}' is not connected")
            return pool

    # --- Maintenance ---

    def cleanup_sessions(self) -> int:
        now = time.time()
        with self._state_lock:
            expired = [
                sid
                for sid, s in self._sessions.items()
                if now - s.last_access > settings.session_timeout
            ]
            for sid in expired:
                del self._sessions[sid]
        if expired:
            log.debug("Cleaned up %d expired sessions", len(expired))
        return len(expired)

    # --- Status ---

    def get_status(self) -> dict:
        pools_status = {}
        with self._state_lock:
            for name, pool in self._pools.items():
                pools_status[name] = {
                    "size": pool.get_size(),
                    "free": pool.get_idle_size(),
                    "used": pool.get_size() - pool.get_idle_size(),
                    "min": pool.get_min_size(),
                    "max": pool.get_max_size(),
                }
            sessions_count = len(self._sessions)
            active_default = registry.active
        return {
            "pools": pools_status,
            "sessions": sessions_count,
            "active_default": active_default,
        }


pool_manager = PoolManager()
