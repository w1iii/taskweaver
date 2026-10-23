import os
import signal
import subprocess
from dataclasses import dataclass

from config import Config
from dependencies import DependencyManager

SUCCESS = "success"
FAILED = "failed"
BLOCKED = "blocked"
SKIPPED = "skipped"
CACHED = "cached"

SUCCEEDED_STATUSES = (SUCCESS, SKIPPED, CACHED)


@dataclass
class TaskResult:
    name: str
    status: str
    attempts: int = 0
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    instance: int = 0

    @property
    def ok(self):
        return self.status in SUCCEEDED_STATUSES


class TaskRunner:
    def __init__(self, tasks: list[dict]):
        self.tasks = tasks
        self.results: dict[str, TaskResult] = {}

    def run_all(self) -> list[TaskResult]:
        """Run tasks in dependency order, one at a time."""
        ordered = DependencyManager(self.tasks).get_execution_order()

        for task in ordered:
            result = self._resolve(task)
            self.results[task["name"]] = result

        return [self.results[task["name"]] for task in ordered]

    def _resolve(self, task: dict) -> TaskResult:
        name = task["name"]

        failed_dependencies = [
            dependency
            for dependency in task.get("dependencies", [])
            if not self.results[dependency].ok
        ]

        if failed_dependencies:
            return TaskResult(
                name=name,
                status=BLOCKED,
                error=f"Blocked by failed dependencies: {', '.join(failed_dependencies)}",
            )

        if not task.get("enabled", True):
            return TaskResult(name=name, status=SKIPPED)

        return self._execute(task)

    def _execute(self, task: dict) -> TaskResult:
        name = task["name"]
        command = task["command"]
        timeout = task["timeout"]
        retries = task["retries"]

        result = TaskResult(name=name, status=FAILED)

        for attempt in range(1, retries + 2):
            result.attempts = attempt

            returncode, stdout, stderr, timed_out = self._run_command(command, timeout)

            result.returncode = returncode
            result.stdout = stdout
            result.stderr = stderr

            if timed_out:
                result.error = f"Timed out after {timeout}s"
            elif returncode == 0:
                result.status = SUCCESS
                result.error = None
                return result
            else:
                result.error = f"Exited with code {returncode}"

        return result

    @staticmethod
    def _run_command(command: str, timeout: float):
        """Run one command and return (returncode, stdout, stderr, timed_out)."""
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return process.returncode, stdout, stderr, False
        except subprocess.TimeoutExpired:
            # Kill the whole process group so children die with the shell.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
            stdout, stderr = process.communicate()
            return process.returncode, stdout, stderr, True


def print_results(results: list[TaskResult]) -> None:
    for result in results:
        line = f"[{result.status}] {result.name}"

        if result.attempts > 1:
            line += f" (attempts: {result.attempts})"

        print(line)

        if result.error:
            print(f"          {result.error}")

        if result.status == FAILED and result.stderr.strip():
            print(result.stderr.rstrip())


def run_workflow(path: str = "taskweaver.yaml") -> list[TaskResult]:
    config = Config(path)

    if not config.check_config():
        raise SystemExit(f"Invalid configuration: {path}")

    return TaskRunner(config.config["tasks"]).run_all()


def main() -> int:
    results = run_workflow()
    print_results(results)

    failures = [result for result in results if not result.ok]
    print(f"\n{len(results) - len(failures)}/{len(results)} tasks succeeded")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
