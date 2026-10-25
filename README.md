# TaskWeaver

YAML-driven task runner with dependency-aware parallel execution and a SQLite result cache.

## Quick start

```bash
taskweaver init              # create taskweaver.yaml
taskweaver validate          # check config + dependency graph
taskweaver list              # show execution order
taskweaver run               # run every task
taskweaver run test          # run one task and its dependencies
```

## Configuration

```yaml
project:
  name: Demo

settings:
  max_retries: 3
  timeout: 300
  max_concurrent: 4
  cache: true

tasks:
  - name: lint
    command: "ruff check ."
    inputs:
      - "**/*.py"
      - "pyproject.toml"

  - name: test
    command: "pytest"
    dependencies: [lint]
    retries: 0
    inputs:
      - "**/*.py"
      - "pyproject.toml"
```

Per-task fields: `command`, `dependencies`, `retries`, `timeout`, `enabled`,
`max_parallel`, `inputs`.

## Caching

Only successful runs are cached. A task's fingerprint covers:

- task config (`command`, `timeout`, `retries`, `max_parallel`)
- SHA-256 of every file matched by `inputs`
- fingerprints of all dependencies (changes cascade downstream)

`inputs` globs are resolved relative to the working directory. Without `inputs`,
only config changes invalidate a cached result — add globs to make source edits
trigger reruns. Keep globs scoped to source files; broad patterns can include
generated or cache files and cause perpetual cache misses.

Tasks with `max_parallel > 1` are never cached: every run executes all instances.

Skip cache lookups with `--no-cache` (before the subcommand). Runs are still
recorded in history. `cache: false` in settings disables both.

## History

`taskweaver history` lists recent runs — success, failure, blocked, cached, and
skipped — newest first. Filter with `--task NAME`, limit with `--limit N`.
History is append-only; `taskweaver clear-cache` clears cached results but keeps it.
