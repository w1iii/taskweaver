Checkpoint 1 — Configuration foundation
Current focus
- Load YAML safely.
- Validate configuration sections and task structure.
- Reject duplicate and invalid names.
- Define defaults for retries, timeouts, and enabled state.



Checkpoint 2 — Dependency validation
- Confirm every dependency references an existing task.
- Reject self-dependencies.
- Detect circular dependencies.
- Produce a valid task execution order.



Checkpoint 3 — Sequential command runner
- Execute one command at a time.
- Check process exit codes.
- Capture standard output and errors.
- Stop dependent tasks when prerequisites fail.



Checkpoint 4 — Retries and timeouts
- Apply global defaults.
- Respect per-task overrides.
- Retry failed commands up to the configured limit.
- Terminate commands that exceed their timeout.



Checkpoint 5 — CLI
- Run a named task.
- Run the entire workflow.
- Display task status and errors.
- Add a configuration-validation command.



Checkpoint 6 — Parallel execution
- Run independent tasks concurrently.
- Enforce dependency constraints.
- Limit the number of concurrent processes.



Checkpoint 7 — Caching and persistence
- Fingerprint task inputs and configuration.
- Skip tasks whose cached results remain valid.
- Store execution history and metadata, potentially using SQLite.



Checkpoint 8 — Triggers and polish
- Add file-change, Git, or scheduled triggers.
- Improve logs, diagnostics, documentation, and automated tests.
