import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from runner import CACHED, SUCCESS, TaskResult

DEFAULT_CACHE_PATH = ".taskweaver/cache.sqlite3"
CACHE_VERSION = 1


def compute_fingerprint(task: dict) -> str:
    """Stable sha256 over every task field that affects the outcome."""
    payload = {
        "version": CACHE_VERSION,
        "name": task["name"],
        "command": task["command"],
        "timeout": task.get("timeout"),
        "retries": task.get("retries"),
        "max_parallel": task.get("max_parallel", 1),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Cache:
    """SQLite-backed cache of successful task results."""

    def __init__(self, path: str | None = None):
        self.path = Path(path or DEFAULT_CACHE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                fingerprint TEXT PRIMARY KEY,
                task_name   TEXT NOT NULL,
                command     TEXT NOT NULL,
                status      TEXT NOT NULL,
                returncode  INTEGER,
                stdout      TEXT,
                stderr      TEXT,
                error       TEXT,
                executed_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, fingerprint: str) -> TaskResult | None:
        """Return a CACHED TaskResult on a successful hit, else None."""
        row = self._conn.execute(
            "SELECT task_name, status, returncode, stdout, stderr, error "
            "FROM results WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()

        if row is None or row["status"] != SUCCESS:
            return None

        return TaskResult(
            name=row["task_name"],
            status=CACHED,
            returncode=row["returncode"],
            stdout=row["stdout"] or "",
            stderr=row["stderr"] or "",
            error=None,
        )

    def store(self, fingerprint: str, task: dict, result: TaskResult) -> None:
        """Persist a task result. Only successful runs are cached."""
        if result.status != SUCCESS:
            return

        self._conn.execute(
            """
            INSERT OR REPLACE INTO results
                (fingerprint, task_name, command, status, returncode,
                 stdout, stderr, error, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fingerprint,
                task["name"],
                task["command"],
                result.status,
                result.returncode,
                result.stdout,
                result.stderr,
                result.error,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def history(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT task_name, command, status, returncode, executed_at "
            "FROM results ORDER BY executed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> int:
        cursor = self._conn.execute("DELETE FROM results")
        self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
