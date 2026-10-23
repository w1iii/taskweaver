import asyncio
from pathlib import Path

import typer

from config import Config
from dependencies import DependencyManager
from parallel_runner import ParallelRunner
from runner import print_results

app = typer.Typer(
    no_args_is_help=False,
    add_completion=False,
    help="TaskWeaver — YAML-driven task runner.",
)

DEFAULT_CONFIG = "taskweaver.yaml"

SAMPLE_CONFIG = """\
project:
  name: TaskWeaver
  version: "1.0.0"

settings:
  max_retries: 3
  timeout: 300

tasks:
  - name: lint
    command: "ruff check ."

  - name: test
    command: "pytest"
    retries: 0

  - name: build
    command: "python -m build"
    dependencies:
      - lint
      - test
    timeout: 600
"""


def _load_config(path: str) -> Config:
    config = Config(path)
    if config.config is None:
        typer.echo(f"Failed to load configuration: {path}", err=True)
        raise typer.Exit(1)
    if not config.check_config():
        typer.echo(f"Invalid configuration: {path}", err=True)
        raise typer.Exit(1)
    return config


def _collect_with_deps(tasks: list[dict], target: str) -> list[dict]:
    """Return target task plus all transitive dependencies."""
    by_name = {t["name"]: t for t in tasks}
    if target not in by_name:
        typer.echo(f"Unknown task: {target}", err=True)
        raise typer.Exit(1)

    needed: set[str] = set()
    stack = [target]
    while stack:
        name = stack.pop()
        if name in needed:
            continue
        needed.add(name)
        stack.extend(by_name[name].get("dependencies", []))

    return [t for t in tasks if t["name"] in needed]


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    config: str = typer.Option(
        DEFAULT_CONFIG, "--config", "-c", help="Path to taskweaver.yaml"
    ),
):
    """TaskWeaver — YAML-driven task runner."""
    ctx.obj = config
    if ctx.invoked_subcommand is None:
        _run_all(config)


def _run_all(config_path: str) -> None:
    config = _load_config(config_path)
    tasks = config.config["tasks"]
    max_concurrent = config.config.get("settings", {}).get("max_concurrent")
    runner = ParallelRunner(tasks, max_concurrent)
    results = asyncio.run(runner.run_all())
    print_results(results)
    failed = [r for r in results if not r.ok]
    typer.echo(f"\n{len(results) - len(failed)}/{len(results)} tasks succeeded")
    raise typer.Exit(1 if failed else 0)


def _run_single(config_path: str, task_name: str) -> None:
    config = _load_config(config_path)
    subset = _collect_with_deps(config.config["tasks"], task_name)
    max_concurrent = config.config.get("settings", {}).get("max_concurrent")
    runner = ParallelRunner(subset, max_concurrent)
    results = asyncio.run(runner.run_all())
    print_results(results)
    failed = [r for r in results if not r.ok]
    typer.echo(f"\n{len(results) - len(failed)}/{len(results)} tasks succeeded")
    raise typer.Exit(1 if failed else 0)


@app.command()
def run(
    ctx: typer.Context,
    task: str = typer.Argument(None, help="Task name (omit for all)"),
):
    """Run the full workflow or a single task with its dependencies."""
    config_path = ctx.obj
    if task is None:
        _run_all(config_path)
    else:
        _run_single(config_path, task)


@app.command()
def validate(ctx: typer.Context):
    """Validate configuration without running tasks."""
    _load_config(ctx.obj)
    typer.echo("Configuration is valid")


@app.command(name="list")
def list_tasks(ctx: typer.Context):
    """List tasks, their commands, and dependencies."""
    cfg = _load_config(ctx.obj)
    tasks = cfg.config["tasks"]

    try:
        ordered = DependencyManager(tasks).get_execution_order()
    except Exception as e:
        typer.echo(f"Dependency error: {e}", err=True)
        raise typer.Exit(1)

    name_width = max(len(t["name"]) for t in ordered)

    for task in ordered:
        deps = task.get("dependencies", [])
        dep_str = f" <- {', '.join(deps)}" if deps else ""
        enabled = "" if task.get("enabled", True) else "  [disabled]"
        typer.echo(f"  {task['name']:<{name_width}}  {task['command']}{dep_str}{enabled}")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
):
    """Create a sample taskweaver.yaml."""
    path = Path(DEFAULT_CONFIG)
    if path.exists() and not force:
        typer.echo(f"{DEFAULT_CONFIG} already exists (use --force to overwrite)", err=True)
        raise typer.Exit(1)
    path.write_text(SAMPLE_CONFIG)
    typer.echo(f"Created {DEFAULT_CONFIG}")


if __name__ == "__main__":
    app()
