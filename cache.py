import glob
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from runner import CACHED, SUCCESS, TaskResult

DEFAULT_CACHE_PATH = ".taskweaver/cache.sqlite3"
CACHE_VERSION = 1
HASH_CHUNK_SIZE = 1024 * 1024


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_fingerprint(
    task: dict,
    tasks_by_name: dict[str, dict] | None = None,
    base_dir: str | Path = ".",
) -> str:
    """Stable sha256 over task config, input file contents, and dependency fingerprints.

    Input globs are relative to ``base_dir`` (the working directory by default).
    When ``tasks_by_name`` is given, dependency fingerprints cascade so a change
    to any upstream input or command invalidates dependents too.
    """
    return _fingerprint(task, tasks_by_name or {}, Path(base_dir), {}, set())


def _fingerprint(task, tasks_by_name, base_dir, memo, visiting):
    name = task["name"]

    if name in memo:
        return memo[name]

    if name in visiting:
        raise ValueError(f"Circular dependency while fingerprinting '{name}'")
    visiting.add(name)

    payload = {
        "version": CACHE_VERSION,
        "name": name,
        "command": task["command"],
        "timeout": task.get("timeout"),
        "retries": task.get("retries"),
        "max_parallel": task.get("max_parallel", 1),
    }

    inputs = task.get("inputs") or []
    if inputs:
        payload["inputs"] = _fingerprint_inputs(inputs, base_dir)

    dependencies = sorted(set(task.get("dependencies") or []))
    if dependencies and tasks_by_name:
        payload["dependencies"] = {
            dependency: _fingerprint(
                tasks_by_name[dependency], tasks_by_name, base_dir, memo, visiting
            )
            for dependency in dependencies
        }

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    visiting.discard(name)
    memo[name] = fingerprint
    return fingerprint


def _fingerprint_inputs(patterns, base_dir):
    """Hash every file matched by the globs, keyed by path for determinism."""
    files: dict[str, Path] = {}

    for pattern in patterns:
        for match in glob.glob(pattern, root_dir=str(base_dir), recursive=True):
            path = Path(match)
            if not path.is_absolute():
                path = base_dir / path
            if path.is_file():
                files[_relative_key(path, base_dir)] = path

    entries = [{"path": key, **_hash_file(files[key])} for key in sorted(files)]
    return {"patterns": sorted(set(patterns)), "files": entries}


def _hash_file(path: Path) -> dict:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
                digest.update(chunk)
        return {"sha256": digest.hexdigest()}
    except OSError:
        # Unreadable files must still change the fingerprint when access changes.
        return {"sha256": None, "unreadable": True}


def _relative_key(path: Path, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


class Cache:
    """SQLite-backed result cache plus append-only execution history."""

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
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name   TEXT NOT NULL,
                command     TEXT NOT NULL,
                status      TEXT NOT NULL,
                attempts    INTEGER NOT NULL DEFAULT 0,
                returncode  INTEGER,
                stdout      TEXT,
                stderr      TEXT,
                error       TEXT,
                instance    INTEGER NOT NULL DEFAULT 0,
                executed_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_task ON runs (task_name, id DESC)"
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
                _timestamp(),
            ),
        )
        self._conn.commit()

    def record_run(self, task: dict, result: TaskResult) -> None:
        """Append one execution to history, regardless of status or cache use."""
        self._conn.execute(
            """
            INSERT INTO runs
                (task_name, command, status, attempts, returncode,
                 stdout, stderr, error, instance, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task["name"],
                task["command"],
                result.status,
                result.attempts,
                result.returncode,
                result.stdout,
                result.stderr,
                result.error,
                result.instance,
                _timestamp(),
            ),
        )
        self._conn.commit()

    def history(self, limit: int = 20, task_name: str | None = None) -> list[dict]:
        """Return recent executions, newest first, optionally for one task."""
        if task_name is None:
            rows = self._conn.execute(
                "SELECT task_name, command, status, attempts, returncode, error, "
                "instance, executed_at FROM runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT task_name, command, status, attempts, returncode, error, "
                "instance, executed_at FROM runs WHERE task_name = ? "
                "ORDER BY id DESC LIMIT ?",
                (task_name, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> int:
        """Remove cached results. Execution history is kept."""
        cursor = self._conn.execute("DELETE FROM results")
        self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
