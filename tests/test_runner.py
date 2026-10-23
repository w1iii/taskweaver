import sys
import time

from runner import (
    BLOCKED,
    FAILED,
    SKIPPED,
    SUCCESS,
    TaskResult,
    TaskRunner,
    print_results,
)


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


class TestTaskResult:
    def test_ok_for_success(self):
        assert TaskResult("a", SUCCESS).ok is True

    def test_ok_for_skipped(self):
        assert TaskResult("a", SKIPPED).ok is True

    def test_not_ok_for_failed(self):
        assert TaskResult("a", FAILED).ok is False

    def test_not_ok_for_blocked(self):
        assert TaskResult("a", BLOCKED).ok is False


class TestSequentialExecution:
    def test_success_command(self):
        tasks = [make_task("a", f"{sys.executable} -c 'print(1)'")]
        results = TaskRunner(tasks).run_all()
        assert len(results) == 1
        assert results[0].status == SUCCESS
        assert results[0].returncode == 0
        assert "1" in results[0].stdout

    def test_failed_command(self):
        tasks = [make_task("a", f"{sys.executable} -c 'raise SystemExit(2)'")]
        results = TaskRunner(tasks).run_all()
        assert results[0].status == FAILED
        assert results[0].returncode == 2
        assert "Exited with code 2" in results[0].error

    def test_stderr_captured(self):
        tasks = [
            make_task(
                "a",
                f"{sys.executable} -c 'import sys; sys.stderr.write(\"oops\"); sys.exit(1)'",
            )
        ]
        results = TaskRunner(tasks).run_all()
        assert results[0].status == FAILED
        assert "oops" in results[0].stderr

    def test_dependency_order_respected(self):
        # b depends on a; a must run first
        tasks = [
            make_task("b", f"{sys.executable} -c 'print(\"b\")'", dependencies=["a"]),
            make_task("a", f"{sys.executable} -c 'print(\"a\")'"),
        ]
        results = TaskRunner(tasks).run_all()
        names = [r.name for r in results]
        assert names.index("a") < names.index("b")

    def test_blocked_by_failed_dependency(self):
        tasks = [
            make_task("a", f"{sys.executable} -c 'raise SystemExit(1)'"),
            make_task("b", f"{sys.executable} -c 'print(1)'", dependencies=["a"]),
        ]
        results = TaskRunner(tasks).run_all()
        by_name = {r.name: r for r in results}
        assert by_name["a"].status == FAILED
        assert by_name["b"].status == BLOCKED
        assert "a" in by_name["b"].error

    def test_blocked_cascades(self):
        tasks = [
            make_task("a", f"{sys.executable} -c 'raise SystemExit(1)'"),
            make_task("b", dependencies=["a"]),
            make_task("c", dependencies=["b"]),
        ]
        results = TaskRunner(tasks).run_all()
        by_name = {r.name: r for r in results}
        assert by_name["b"].status == BLOCKED
        assert by_name["c"].status == BLOCKED

    def test_disabled_task_skipped(self):
        tasks = [make_task("a", f"{sys.executable} -c 'print(1)'", enabled=False)]
        results = TaskRunner(tasks).run_all()
        assert results[0].status == SKIPPED

    def test_disabled_dependency_counts_as_ok(self):
        # disabled task is "ok" (skipped), so dependents should run
        tasks = [
            make_task("a", enabled=False),
            make_task("b", f"{sys.executable} -c 'print(1)'", dependencies=["a"]),
        ]
        results = TaskRunner(tasks).run_all()
        by_name = {r.name: r for r in results}
        assert by_name["a"].status == SKIPPED
        assert by_name["b"].status == SUCCESS


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
        results = TaskRunner(tasks).run_all()
        assert results[0].status == SUCCESS
        assert results[0].attempts == 2

    def test_exhausted_retries(self):
        tasks = [make_task("a", f"{sys.executable} -c 'raise SystemExit(1)'", retries=2)]
        results = TaskRunner(tasks).run_all()
        assert results[0].status == FAILED
        assert results[0].attempts == 3  # initial + 2 retries

    def test_no_retry_on_success(self):
        tasks = [make_task("a", f"{sys.executable} -c 'print(1)'", retries=3)]
        results = TaskRunner(tasks).run_all()
        assert results[0].status == SUCCESS
        assert results[0].attempts == 1


class TestTimeout:
    def test_timeout_kills_process(self):
        tasks = [make_task("a", f"{sys.executable} -c 'import time; time.sleep(10)'", timeout=0.5)]
        start = time.monotonic()
        results = TaskRunner(tasks).run_all()
        elapsed = time.monotonic() - start
        assert results[0].status == FAILED
        assert "Timed out" in results[0].error
        assert elapsed < 5  # not waiting full 10s

    def test_timeout_allows_fast_process(self):
        tasks = [make_task("a", f"{sys.executable} -c 'print(1)'", timeout=10)]
        results = TaskRunner(tasks).run_all()
        assert results[0].status == SUCCESS


class TestPrintResults:
    def test_print_success(self, capsys):
        print_results([TaskResult("a", SUCCESS)])
        out = capsys.readouterr().out
        assert "[success] a" in out

    def test_print_failed_with_error(self, capsys):
        r = TaskResult("a", FAILED, error="Exited with code 1")
        print_results([r])
        out = capsys.readouterr().out
        assert "[failed] a" in out
        assert "Exited with code 1" in out

    def test_print_attempts_when_gt_1(self, capsys):
        r = TaskResult("a", FAILED, attempts=3, error="fail")
        print_results([r])
        out = capsys.readouterr().out
        assert "attempts: 3" in out

    def test_print_stderr_on_failed(self, capsys):
        r = TaskResult("a", FAILED, error="x", stderr="some error")
        print_results([r])
        out = capsys.readouterr().out
        assert "some error" in out
