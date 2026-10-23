import pytest

from dependencies import DependencyError, DependencyManager


def make_task(name, deps=None, **extra):
    task = {"name": name, "command": f"echo {name}"}
    if deps:
        task["dependencies"] = deps
    task.update(extra)
    return task


class TestValidateDependencies:
    def test_valid_dependencies_pass(self):
        tasks = [make_task("a"), make_task("b", ["a"]), make_task("c", ["a", "b"])]
        DependencyManager(tasks).validate_dependencies()

    def test_unknown_dependency_raises(self):
        tasks = [make_task("a", ["ghost"])]
        with pytest.raises(DependencyError, match="unknown task 'ghost'"):
            DependencyManager(tasks).validate_dependencies()

    def test_self_dependency_raises(self):
        tasks = [make_task("a", ["a"])]
        with pytest.raises(DependencyError, match="cannot depend on itself"):
            DependencyManager(tasks).validate_dependencies()

    def test_non_list_dependencies_raises(self):
        tasks = [{"name": "a", "command": "echo", "dependencies": "not-a-list"}]
        with pytest.raises(DependencyError, match="must be a list"):
            DependencyManager(tasks).validate_dependencies()

    def test_non_string_dependency_raises(self):
        tasks = [{"name": "a", "command": "echo", "dependencies": [123]}]
        with pytest.raises(DependencyError, match="must be task names"):
            DependencyManager(tasks).validate_dependencies()


class TestExecutionOrder:
    def test_single_task(self):
        tasks = [make_task("a")]
        order = DependencyManager(tasks).get_execution_order()
        assert [t["name"] for t in order] == ["a"]

    def test_linear_chain(self):
        tasks = [make_task("c", ["b"]), make_task("b", ["a"]), make_task("a")]
        order = DependencyManager(tasks).get_execution_order()
        names = [t["name"] for t in order]
        assert names.index("a") < names.index("b") < names.index("c")

    def test_diamond(self):
        tasks = [
            make_task("a"),
            make_task("b", ["a"]),
            make_task("c", ["a"]),
            make_task("d", ["b", "c"]),
        ]
        order = DependencyManager(tasks).get_execution_order()
        names = [t["name"] for t in order]
        assert names[0] == "a"
        assert names[-1] == "d"
        assert names.index("b") < names.index("d")
        assert names.index("c") < names.index("d")

    def test_independent_tasks_all_present(self):
        tasks = [make_task("x"), make_task("y"), make_task("z")]
        order = DependencyManager(tasks).get_execution_order()
        assert sorted(t["name"] for t in order) == ["x", "y", "z"]

    def test_cycle_raises(self):
        tasks = [make_task("a", ["b"]), make_task("b", ["a"])]
        with pytest.raises(DependencyError, match="Circular dependency"):
            DependencyManager(tasks).get_execution_order()

    def test_self_cycle_raises(self):
        tasks = [make_task("a", ["a"])]
        with pytest.raises(DependencyError):
            DependencyManager(tasks).get_execution_order()

    def test_longer_cycle_raises(self):
        tasks = [
            make_task("a", ["c"]),
            make_task("b", ["a"]),
            make_task("c", ["b"]),
        ]
        with pytest.raises(DependencyError, match="Circular dependency"):
            DependencyManager(tasks).get_execution_order()

    def test_returned_tasks_preserve_fields(self):
        tasks = [make_task("a", extra_field="kept")]
        order = DependencyManager(tasks).get_execution_order()
        assert order[0]["extra_field"] == "kept"
