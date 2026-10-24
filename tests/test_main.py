from typer.testing import CliRunner

from main import app

runner = CliRunner()


def write_cfg(tmp_path, text):
    path = tmp_path / "taskweaver.yaml"
    path.write_text(text)
    return path


def test_validate_accepts_valid_config(tmp_path):
    path = write_cfg(
        tmp_path,
        """
        project:
          name: Test
        tasks:
          - name: a
            command: "echo a"
        """,
    )
    result = runner.invoke(app, ["--config", str(path), "validate"])
    assert result.exit_code == 0
    assert "Configuration is valid" in result.output


def test_validate_rejects_unknown_dependency(tmp_path):
    path = write_cfg(
        tmp_path,
        """
        project:
          name: Test
        tasks:
          - name: a
            command: "echo a"
            dependencies: [missing]
        """,
    )
    result = runner.invoke(app, ["--config", str(path), "validate"])
    assert result.exit_code == 1
    assert "Dependency error" in result.output


def test_validate_rejects_cycle(tmp_path):
    path = write_cfg(
        tmp_path,
        """
        project:
          name: Test
        tasks:
          - name: a
            command: "echo a"
            dependencies: [b]
          - name: b
            command: "echo b"
            dependencies: [a]
        """,
    )
    result = runner.invoke(app, ["--config", str(path), "validate"])
    assert result.exit_code == 1
    assert "Circular" in result.output


def test_run_rejects_cycle_without_crashing(tmp_path):
    path = write_cfg(
        tmp_path,
        """
        project:
          name: Test
        settings:
          cache: false
        tasks:
          - name: a
            command: "echo a"
            dependencies: [b]
          - name: b
            command: "echo b"
            dependencies: [a]
        """,
    )
    result = runner.invoke(app, ["--config", str(path), "run"])
    assert result.exit_code == 1
    assert "Dependency error" in result.output
    assert "Traceback" not in result.output


def test_run_unknown_task_exits_1(tmp_path):
    path = write_cfg(
        tmp_path,
        """
        project:
          name: Test
        settings:
          cache: false
        tasks:
          - name: a
            command: "echo a"
        """,
    )
    result = runner.invoke(app, ["--config", str(path), "run", "nope"])
    assert result.exit_code == 1
    assert "Unknown task: nope" in result.output
