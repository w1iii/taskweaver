import yaml


class Config:
    def __init__(self, path="taskweaver.yaml"):
        self.config = None

        try:
            with open(path, "r") as f:
                self.config = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            print(f"Failed to load configuration: {e}")

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

            # Reject non-string and empty names
            if not isinstance(name, str) or not name.strip():
                print(f"Invalid task name: {name!r}")
                return False

            # Reject duplicate names
            if name in names:
                print(f"Duplicate task name: {name}")
                return False

            names.add(name)

        print(f"Validated task names: {names}")
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
