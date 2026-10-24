import sys

import pytest

from dependencies import DependencyError
from parallel_runner import ParallelRunner, compute_depths, run_workflow_parallel
from runner import BLOCKED, FAILED, SUCCESS


def make_task(name, command=None, **extra):
    task = {
        "name": name,
        "command": command or f"echo {name}",
        "retries": 0,
        "timeout": 30,
        "enabled": True,
    }
    task.update(extra)
    return task


class TestComputeDepths:
    def test_single_root(self):
        tasks = [make_task("a")]
        assert compute_depths(tasks) == {"a": 0}

    def test_chain(self):
        tasks = [
            make_task("a"),
            make_task("b", dependencies=["a"]),
            make_task("c", dependencies=["b"]),
        ]
        depths = compute_depths(tasks)
        assert depths == {"a": 0, "b": 1, "c": 2}

    def test_diamond(self):
        tasks = [
            make_task("a"),
            make_task("b", dependencies=["a"]),
            make_task("c", dependencies=["a"]),
            make_task("d", dependencies=["b", "c"]),
        ]
        depths = compute_depths(tasks)
        assert depths == {"a": 0, "b": 1, "c": 1, "d": 2}

    def test_multiple_roots(self):
        tasks = [make_task("a"), make_task("b")]
        assert compute_depths(tasks) == {"a": 0, "b": 0}


class TestParallelExecution:
    def test_single_task(self):
        tasks = [make_task("a", f"{sys.executable} -c 'print(1)'")]
        results = run_workflow_parallel(tasks)
        assert len(results) == 1
        assert results[0].status == SUCCESS

    def test_independent_tasks_all_succeed(self):
        tasks = [
            make_task("a", f"{sys.executable} -c 'print(1)'"),
            make_task("b", f"{sys.executable} -c 'print(2)'"),
            make_task("c", f"{sys.executable} -c 'print(3)'"),
        ]
        results = run_workflow_parallel(tasks)
        assert all(r.status == SUCCESS for r in results)
        assert len(results) == 3

    def test_dependency_order(self):
        tasks = [
            make_task("b", f"{sys.executable} -c 'print(1)'", dependencies=["a"]),
            make_task("a", f"{sys.executable} -c 'print(1)'"),
        ]
        results = run_workflow_parallel(tasks)
        names = [r.name for r in results]
        assert names.index("a") < names.index("b")

    def test_blocked_by_failed_dependency(self):
        tasks = [
            make_task("a", f"{sys.executable} -c 'raise SystemExit(1)'"),
            make_task("b", f"{sys.executable} -c 'print(1)'", dependencies=["a"]),
        ]
        results = run_workflow_parallel(tasks)
        by_name = {r.name: r for r in results}
        assert by_name["a"].status == FAILED
        assert by_name["b"].status == BLOCKED

    def test_blocked_cascades(self):
        tasks = [
            make_task("a", f"{sys.executable} -c 'raise SystemExit(1)'"),
            make_task("b", dependencies=["a"]),
            make_task("c", dependencies=["b"]),
        ]
        results = run_workflow_parallel(tasks)
        by_name = {r.name: r for r in results}
        assert by_name["b"].status == BLOCKED
        assert by_name["c"].status == BLOCKED

    def test_max_concurrent_limits(self):
        # 4 tasks, max_concurrent=2 — all should still succeed
        tasks = [make_task(f"t{i}", f"{sys.executable} -c 'print(1)'") for i in range(4)]
        runner = ParallelRunner(tasks, max_concurrent=2)
        import asyncio
        results = asyncio.run(runner.run_all())
        assert all(r.status == SUCCESS for r in results)
        assert len(results) == 4

    def test_diamond_execution(self):
        tasks = [
            make_task("a", f"{sys.executable} -c 'print(1)'"),
            make_task("b", f"{sys.executable} -c 'print(1)'", dependencies=["a"]),
            make_task("c", f"{sys.executable} -c 'print(1)'", dependencies=["a"]),
            make_task("d", f"{sys.executable} -c 'print(1)'", dependencies=["b", "c"]),
        ]
        results = run_workflow_parallel(tasks)
        assert all(r.status == SUCCESS for r in results)
        # d must come after b and c in results list
        names = [r.name for r in results]
        assert names.index("b") < names.index("d")
        assert names.index("c") < names.index("d")


class TestCycleDetection:
    def test_two_task_cycle_raises(self):
        tasks = [
            make_task("a", dependencies=["b"]),
            make_task("b", dependencies=["a"]),
        ]
        with pytest.raises(DependencyError, match="Circular"):
            run_workflow_parallel(tasks)

    def test_longer_cycle_raises(self):
        tasks = [
            make_task("a", dependencies=["c"]),
            make_task("b", dependencies=["a"]),
            make_task("c", dependencies=["b"]),
        ]
        with pytest.raises(DependencyError, match="Circular"):
            run_workflow_parallel(tasks)

    def test_unknown_dependency_raises(self):
        tasks = [make_task("a", dependencies=["missing"])]
        with pytest.raises(DependencyError, match="unknown task"):
            run_workflow_parallel(tasks)


class TestRetries:
    def test_retry_on_failure(self, tmp_path):
        counter = tmp_path / "count"
        script = (
            f"import sys, pathlib; "
            f"c = pathlib.Path({str(counter)!r}); "
            f"n = int(c.read_text()) if c.exists() else 0; "
            f"c.write_text(str(n+1)); "
            f"sys.exit(0 if n >= 1 else 1)"
        )
        tasks = [make_task("a", f"{sys.executable} -c \"{script}\"", retries=1)]
        results = run_workflow_parallel(tasks)
        assert results[0].status == SUCCESS
        assert results[0].attempts == 2

    def test_exhausted_retries(self):
        tasks = [make_task("a", f"{sys.executable} -c 'raise SystemExit(1)'", retries=2)]
        results = run_workflow_parallel(tasks)
        assert results[0].status == FAILED
        assert results[0].attempts == 3


class TestTimeout:
    def test_timeout_kills(self):
        tasks = [
            make_task("a", f"{sys.executable} -c 'import time; time.sleep(10)'", timeout=0.5)
        ]
        results = run_workflow_parallel(tasks)
        assert results[0].status == FAILED
        assert "Timed out" in results[0].error

    def test_fast_process_succeeds(self):
        tasks = [make_task("a", f"{sys.executable} -c 'print(1)'", timeout=10)]
        results = run_workflow_parallel(tasks)
        assert results[0].status == SUCCESS
