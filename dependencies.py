from collections import deque


class DependencyError(Exception):
    """Raised when task dependencies are invalid."""


class DependencyManager:
    def __init__(self, tasks: list[dict]):
        self.tasks = tasks
        self.tasks_by_name = {task["name"]: task for task in tasks}

    def validate_dependencies(self) -> None:
        """Check that dependencies exist and tasks don't depend on themselves."""
        for task in self.tasks:
            name = task["name"]
            dependencies = task.get("dependencies", [])

            if not isinstance(dependencies, list):
                raise DependencyError(f"Dependencies for '{name}' must be a list.")

            for dependency in dependencies:
                if not isinstance(dependency, str):
                    raise DependencyError(
                        f"Dependencies for '{name}' must be task names."
                    )

                if dependency == name:
                    raise DependencyError(f"Task '{name}' cannot depend on itself.")

                if dependency not in self.tasks_by_name:
                    raise DependencyError(
                        f"Task '{name}' depends on unknown task '{dependency}'."
                    )

    def get_execution_order(self) -> list[dict]:
        """Return tasks in dependency-safe order using Kahn's algorithm."""
        self.validate_dependencies()

        # Count how many prerequisites each task has.
        in_degree = {
            task["name"]: len(task.get("dependencies", [])) for task in self.tasks
        }

        # Map each prerequisite to the tasks that depend on it.
        dependents = {name: [] for name in self.tasks_by_name}

        for task in self.tasks:
            for dependency in task.get("dependencies", []):
                dependents[dependency].append(task["name"])

        # Tasks with no prerequisites can run first.
        ready = deque(name for name, count in in_degree.items() if count == 0)

        ordered_names = []

        while ready:
            name = ready.popleft()
            ordered_names.append(name)

            for dependent in dependents[name]:
                in_degree[dependent] -= 1

                if in_degree[dependent] == 0:
                    ready.append(dependent)

        # If not every task was processed, a cycle exists.
        if len(ordered_names) != len(self.tasks):
            raise DependencyError("Circular dependency detected between tasks.")

        return [self.tasks_by_name[name] for name in ordered_names]
