import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass

from dependencies import DependencyManager
from runner import BLOCKED, FAILED, SKIPPED, SUCCESS, TaskResult


def compute_depths(tasks: list[dict]) -> dict[str, int]:
    """BFS depth: roots = 0, each dependent = max(dep depths) + 1."""
    deps_of = {t["name"]: set(t.get("dependencies", [])) for t in tasks}
    depth: dict[str, int] = {n: 0 for n, d in deps_of.items() if not d}

    changed = True
    while changed:
        changed = False
        for name, deps in deps_of.items():
            if name in depth:
                continue
            if deps and all(d in depth for d in deps):
                depth[name] = max(depth[d] for d in deps) + 1
                changed = True

    return depth


class ParallelRunner:
    def __init__(self, tasks: list[dict], max_concurrent: int | None = None):
        self.tasks = tasks
        self.tasks_by_name = {t["name"]: t for t in tasks}
        self.max_concurrent = max_concurrent or os.cpu_count() or 4
        self.depths = compute_depths(tasks)
        self.results: list[TaskResult] = []
        self.task_status: dict[str, str] = {}
        self.dependents: dict[str, list[str]] = defaultdict(list)
        for t in tasks:
            for d in t.get("dependencies", []):
                self.dependents[d].append(t["name"])

    async def run_all(self) -> list[TaskResult]:
        DependencyManager(self.tasks).validate_dependencies()

        ready: asyncio.PriorityQueue = asyncio.PriorityQueue()
        in_degree = {
            name: len(self.tasks_by_name[name].get("dependencies", []))
            for name in self.tasks_by_name
        }

        for name, deg in in_degree.items():
            if deg == 0:
                await ready.put((self.depths[name], name))

        global_sem = asyncio.Semaphore(self.max_concurrent)
        running: dict[asyncio.Task, str] = {}
        done_event = asyncio.Event()

        def on_done(t: asyncio.Task):
            done_event.set()

        while len(self.task_status) < len(self.tasks):
            while not ready.empty() and len(running) < self.max_concurrent:
                _, name = await ready.get()
                if name in self.task_status:
                    continue
                t = asyncio.create_task(self._run_task(name, global_sem))
                running[t] = name
                t.add_done_callback(on_done)

            if not running:
                break

            done_event.clear()
            finished, _ = await asyncio.wait(
                running.keys(), return_when=asyncio.FIRST_COMPLETED
            )

            for t in finished:
                name = running.pop(t)
                instances = t.result()
                self._record(name, instances, in_degree, ready)

        return self.results

    def _record(
        self,
        name: str,
        instances: list[TaskResult],
        in_degree: dict[str, int],
        ready: asyncio.PriorityQueue,
    ):
        any_failed = any(not r.ok for r in instances)
        status = FAILED if any_failed else SUCCESS
        self.task_status[name] = status
        self.results.extend(instances)

        for dep_name in self.dependents[name]:
            if dep_name in self.task_status:
                continue
            if status == FAILED:
                self._block(dep_name, [name])
            else:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    ready.put_nowait((self.depths[dep_name], dep_name))

    def _block(self, name: str, failed_deps: list[str]):
        if name in self.task_status:
            return
        self.task_status[name] = BLOCKED
        self.results.append(
            TaskResult(
                name=name,
                status=BLOCKED,
                error=f"Blocked by failed dependencies: {', '.join(failed_deps)}",
            )
        )
        for child in self.dependents[name]:
            self._block(child, [name])

    async def _run_task(
        self, name: str, global_sem: asyncio.Semaphore
    ) -> list[TaskResult]:
        task = self.tasks_by_name[name]
        max_parallel = task.get("max_parallel", 1)
        per_task_sem = asyncio.Semaphore(max_parallel)

        async def run_instance(instance_id: int) -> TaskResult:
            async with global_sem:
                async with per_task_sem:
                    return await self._execute(task, instance_id)

        return await asyncio.gather(
            *(run_instance(i) for i in range(max_parallel))
        )

    async def _execute(self, task: dict, instance: int) -> TaskResult:
        name = task["name"]
        command = task["command"]
        timeout = task.get("timeout", 300)
        retries = task.get("retries", 0)

        result = TaskResult(name=name, status=FAILED, instance=instance)

        for attempt in range(1, retries + 2):
            result.attempts = attempt
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except Exception as e:
                result.error = str(e)
                return result

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            async def stream(reader, sink):
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    text = line.decode(errors="replace").rstrip()
                    sink.append(text)
                    print(f"[{name}] {text}")

            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        stream(proc.stdout, stdout_lines),
                        stream(proc.stderr, stderr_lines),
                        proc.wait(),
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                result.error = f"Timed out after {timeout}s"
                result.stdout = "\n".join(stdout_lines)
                result.stderr = "\n".join(stderr_lines)
                continue

            returncode = proc.returncode
            result.returncode = returncode
            result.stdout = "\n".join(stdout_lines)
            result.stderr = "\n".join(stderr_lines)

            if returncode == 0:
                result.status = SUCCESS
                result.error = None
                return result
            result.error = f"Exited with code {returncode}"

        return result


def run_workflow_parallel(
    tasks: list[dict], max_concurrent: int | None = None
) -> list[TaskResult]:
    runner = ParallelRunner(tasks, max_concurrent)
    return asyncio.run(runner.run_all())
