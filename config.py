import yaml

DEFAULTS = {
    "retries": 0,
    "timeout": 300,
    "enabled": True,
}


class Config:
    def __init__(self, path="taskweaver.yaml"):
        self.config = None

        try:
            with open(path, "r") as f:
                self.config = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            print(f"Failed to load configuration: {e}")

    @staticmethod
    def _is_count(value):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    @staticmethod
    def _is_positive(value):
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float)) and value > 0

    def check_settings(self):
        settings = self.config.get("settings", {})

        if not isinstance(settings, dict):
            print("Settings section must be a mapping")
            return False

        if "max_retries" in settings and not self._is_count(settings["max_retries"]):
            print(f"Invalid max_retries: {settings['max_retries']!r}")
            return False

        if "timeout" in settings and not self._is_positive(settings["timeout"]):
            print(f"Invalid timeout: {settings['timeout']!r}")
            return False

        if "max_concurrent" in settings and not self._is_positive(settings["max_concurrent"]):
            print(f"Invalid max_concurrent: {settings['max_concurrent']!r}")
            return False

        return True

    def apply_defaults(self, tasks=None):
        """Fill retries, timeout, and enabled for every task, honoring per-task overrides."""
        if tasks is None:
            tasks = self.config.get("tasks", [])

        settings = self.config.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}

        global_retries = settings.get("max_retries", DEFAULTS["retries"])
        global_timeout = settings.get("timeout", DEFAULTS["timeout"])

        for task in tasks:
            task.setdefault("retries", global_retries)
            task.setdefault("timeout", global_timeout)
            task.setdefault("enabled", DEFAULTS["enabled"])

        return tasks

    def check_tasks(self):
        # Validate the overall configuration
        if not isinstance(self.config, dict):
            print("Configuration must be a YAML mapping")
            return False

        # Check that the tasks key exists
        if "tasks" not in self.config:
            print("Missing tasks section in config")
            return False

        tasks = self.config["tasks"]

        # Validate the tasks list
        if not isinstance(tasks, list):
            print("Tasks must be a list")
            return False

        if len(tasks) == 0:
            print("Task list cannot be empty")
            return False

        if not self.check_settings():
            return False

        names = set()

        for task in tasks:
            # Each task must be a dictionary
            if not isinstance(task, dict):
                print("Each task must be a dictionary")
                return False

            # Each task must have a name
            if "name" not in task:
                print("Missing task name")
                return False

            name = task["name"]

            # YAML 1.1 turns bare off/on/yes/no into booleans
            if isinstance(name, bool):
                print(f"Task name {name!r} was read as a boolean; quote it in YAML")
                return False

            # Reject non-string and empty names
            if not isinstance(name, str) or not name.strip():
                print(f"Invalid task name: {name!r}")
                return False

            # Reject duplicate names
            if name in names:
                print(f"Duplicate task name: {name}")
                return False

            # Each task must run something
            if "command" not in task:
                print(f"Task '{name}' is missing a command")
                return False

            command = task["command"]
            if not isinstance(command, str) or not command.strip():
                print(f"Task '{name}' has an invalid command: {command!r}")
                return False

            if "retries" in task and not self._is_count(task["retries"]):
                print(f"Invalid retries for task '{name}': {task['retries']!r}")
                return False

            if "timeout" in task and not self._is_positive(task["timeout"]):
                print(f"Invalid timeout for task '{name}': {task['timeout']!r}")
                return False

            if "max_parallel" in task and not self._is_positive(task["max_parallel"]):
                print(f"Invalid max_parallel for task '{name}': {task['max_parallel']!r}")
                return False

            if "enabled" in task and not isinstance(task["enabled"], bool):
                print(f"Invalid enabled for task '{name}': {task['enabled']!r}")
                return False

            names.add(name)

        self.apply_defaults(tasks)

        return True

    def check_config(self):
        if not isinstance(self.config, dict):
            print("Configuration is missing or invalid")
            return False

        if "project" not in self.config:
            print("Missing project section in config")
            return False

        if not isinstance(self.config["project"], dict):
            print("Project section must be a mapping")
            return False

        if not self.check_tasks():
            return False

        print("Configuration is valid")
        return True


if __name__ == "__main__":
    config = Config()

    if config.check_config():
        print(config.config)
