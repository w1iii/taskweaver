import sys

import pytest

from cache import Cache, compute_fingerprint
from parallel_runner import ParallelRunner
from runner import BLOCKED, CACHED, FAILED, SKIPPED, SUCCESS, TaskResult


def make_task(name="a", command=None, **extra):
    task = {
        "name": name,
        "command": command or f"{sys.executable} -c 'print(1)'",
        "retries": 0,
        "timeout": 30,
    }
    task.update(extra)
    return task


class TestFingerprint:
    def test_deterministic(self):
        task = make_task()
        assert compute_fingerprint(task) == compute_fingerprint(dict(task))

    def test_key_order_irrelevant(self):
        a = {"name": "x", "command": "c", "timeout": 1, "retries": 0}
        b = {"retries": 0, "timeout": 1, "command": "c", "name": "x"}
        assert compute_fingerprint(a) == compute_fingerprint(b)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("name", "different"),
            ("command", "different"),
            ("timeout", 999),
            ("retries", 5),
            ("max_parallel", 3),
        ],
    )
    def test_field_change_changes_hash(self, field, value):
        base = make_task()
        changed = make_task(**{field: value})
        assert compute_fingerprint(base) != compute_fingerprint(changed)

    def test_version_included(self):
        # Changing CACHE_VERSION must invalidate all fingerprints.
        import cache

        task = make_task()
        original = compute_fingerprint(task)
        old = cache.CACHE_VERSION
        cache.CACHE_VERSION = old + 1
        try:
            assert compute_fingerprint(task) != original
        finally:
            cache.CACHE_VERSION = old


class TestCacheStoreGet:
    def test_miss_on_empty(self, tmp_path):
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            assert cache.get("nope") is None

    def test_store_then_hit(self, tmp_path):
        task = make_task()
        fp = compute_fingerprint(task)
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            cache.store(fp, task, TaskResult("a", SUCCESS, returncode=0, stdout="ok"))
            hit = cache.get(fp)
            assert hit is not None
            assert hit.status == CACHED
            assert hit.name == "a"
            assert hit.stdout == "ok"
            assert hit.ok is True

    def test_failed_results_not_stored(self, tmp_path):
        task = make_task()
        fp = compute_fingerprint(task)
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            cache.store(fp, task, TaskResult("a", FAILED, returncode=1, error="bad"))
            assert cache.get(fp) is None

    def test_store_replaces_existing(self, tmp_path):
        task = make_task()
        fp = compute_fingerprint(task)
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            cache.store(fp, task, TaskResult("a", SUCCESS, returncode=0, stdout="first"))
            cache.store(fp, task, TaskResult("a", SUCCESS, returncode=0, stdout="second"))
            assert cache.get(fp).stdout == "second"
            assert len(cache.history()) == 1

    def test_persistence_across_instances(self, tmp_path):
        path = str(tmp_path / "c.sqlite3")
        task = make_task()
        fp = compute_fingerprint(task)
        with Cache(path) as cache:
            cache.store(fp, task, TaskResult("a", SUCCESS, returncode=0))
        with Cache(path) as cache:
            assert cache.get(fp) is not None


class TestHistoryAndClear:
    def test_history_records(self, tmp_path):
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            cache.store("fp1", make_task("a"), TaskResult("a", SUCCESS, returncode=0))
            cache.store("fp2", make_task("b"), TaskResult("b", SUCCESS, returncode=0))
            rows = cache.history()
            assert len(rows) == 2
            assert {r["task_name"] for r in rows} == {"a", "b"}

    def test_history_limit(self, tmp_path):
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            for i in range(5):
                cache.store(f"fp{i}", make_task(f"t{i}"), TaskResult(f"t{i}", SUCCESS))
            assert len(cache.history(limit=2)) == 2

    def test_clear(self, tmp_path):
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            cache.store("fp1", make_task("a"), TaskResult("a", SUCCESS))
            assert cache.clear() == 1
            assert cache.history() == []
            assert cache.get("fp1") is None


class TestRunnerIntegration:
    def _run(self, tasks, cache):
        import asyncio

        return asyncio.run(ParallelRunner(tasks, cache=cache).run_all())

    def test_first_run_executes_then_second_run_cached(self, tmp_path):
        task = make_task()
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            first = self._run([task], cache)
            assert first[0].status == SUCCESS

            second = self._run([task], cache)
            assert second[0].status == CACHED
            assert second[0].ok is True

    def test_command_change_invalidates_cache(self, tmp_path):
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            self._run([make_task(command=f"{sys.executable} -c 'print(1)'")], cache)
            changed = self._run(
                [make_task(command=f"{sys.executable} -c 'print(2)'")], cache
            )
            assert changed[0].status == SUCCESS

    def test_failure_not_cached_reruns(self, tmp_path):
        failing = make_task(command=f"{sys.executable} -c 'raise SystemExit(1)'")
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            first = self._run([failing], cache)
            assert first[0].status == FAILED
            second = self._run([failing], cache)
            assert second[0].status == FAILED

    def test_no_cache_always_executes(self, tmp_path):
        task = make_task()
        first = self._run([task], None)
        second = self._run([task], None)
        assert first[0].status == SUCCESS
        assert second[0].status == SUCCESS

    def test_cached_dependency_unblocks_dependent(self, tmp_path):
        tasks = [
            make_task("a"),
            make_task("b", command=f"{sys.executable} -c 'print(2)'", dependencies=["a"]),
        ]
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            self._run(tasks, cache)
            results = self._run(tasks, cache)
            by_name = {r.name: r for r in results}
            assert by_name["a"].status == CACHED
            assert by_name["b"].status == CACHED
            assert all(r.ok for r in results)

    def test_disabled_task_skipped_with_cache(self, tmp_path):
        task = make_task(enabled=False)
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            results = self._run([task], cache)
            assert results[0].status == SKIPPED

    def test_cache_not_stored_when_task_blocked(self, tmp_path):
        tasks = [
            make_task("a", command=f"{sys.executable} -c 'raise SystemExit(1)'"),
            make_task("b", dependencies=["a"]),
        ]
        with Cache(str(tmp_path / "c.sqlite3")) as cache:
            results = self._run(tasks, cache)
            by_name = {r.name: r for r in results}
            assert by_name["b"].status == BLOCKED
            # blocked tasks should not appear in cache
            assert cache.get(compute_fingerprint(tasks[1])) is None
