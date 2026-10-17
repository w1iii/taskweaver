import yaml


class Config:
    def __init__(self):
        try:
            with open("taskweaver.yaml", "r") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(e)

    def check_tasks(self):
        if self.config["tasks"]:
            if type(self.config["tasks"]) is not list:
                print("Tasks is not a list")
                return False
            else:
                print("Task is a list")
                names = set()
                try:
                    tasks = self.config["tasks"]

                    if len(tasks) < 1:
                        print("Empty task list")
                        return False

                    for task in tasks:
                        if task["name"].strip() == "" and isinstance(task["name"], str):
                            print("Empty name found in tasks")
                            return False
                        else:
                            if task["name"] in names:
                                print("Duplicate name: ", task["name"])
                                names.add(task["name"])
                                return False
                            else:
                                names.add(task["name"])
                    print(names)
                    return True
                except Exception as e:
                    print(e)
                    return False
        else:
            print("config tasks does not exist")

    def check_config(self):
        if "project" not in self.config:
            print("Missing project section in config")

        if not self.check_tasks():
            return False

        print(self.config)


if __name__ == "__main__":
    config = Config()
    config.check_tasks()
    # config.check_config()
