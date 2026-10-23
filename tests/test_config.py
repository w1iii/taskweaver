import textwrap

from config import Config


def write_cfg(tmp_path, content: str):
    p = tmp_path / "taskweaver.yaml"
    p.write_text(textwrap.dedent(content))
    return str(p)


class TestConfigLoading:
    def test_valid_config_loads(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: "echo hi"
            """,
        )
        cfg = Config(path)
        assert cfg.config is not None
        assert cfg.check_config() is True

    def test_missing_file(self, tmp_path):
        cfg = Config(str(tmp_path / "nope.yaml"))
        assert cfg.config is None

    def test_invalid_yaml(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("{{{{not yaml")
        cfg = Config(str(p))
        assert cfg.config is None


class TestCheckConfig:
    def test_missing_project_section(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            tasks:
              - name: a
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_project_not_mapping(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project: "just a string"
            tasks:
              - name: a
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_missing_tasks_section(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            """,
        )
        assert Config(path).check_config() is False

    def test_empty_task_list(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks: []
            """,
        )
        assert Config(path).check_config() is False


class TestCheckTasks:
    def test_task_not_dict(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - "not a dict"
            """,
        )
        assert Config(path).check_config() is False

    def test_missing_task_name(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_duplicate_task_names(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: "echo 1"
              - name: a
                command: "echo 2"
            """,
        )
        assert Config(path).check_config() is False

    def test_empty_name_rejected(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: "  "
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_missing_command(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
            """,
        )
        assert Config(path).check_config() is False

    def test_empty_command(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: ""
            """,
        )
        assert Config(path).check_config() is False

    def test_bool_name_rejected(self, tmp_path):
        # YAML 1.1 parses bare off/on/yes/no as booleans
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: on
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False


class TestSettingsValidation:
    def test_invalid_max_retries(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            settings:
              max_retries: -1
            tasks:
              - name: a
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_bool_max_retries_rejected(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            settings:
              max_retries: true
            tasks:
              - name: a
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_invalid_timeout(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            settings:
              timeout: 0
            tasks:
              - name: a
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_invalid_max_concurrent(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            settings:
              max_concurrent: 0
            tasks:
              - name: a
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False

    def test_settings_not_mapping(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            settings: "not a map"
            tasks:
              - name: a
                command: "echo"
            """,
        )
        assert Config(path).check_config() is False


class TestDefaults:
    def test_defaults_applied(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: "echo"
            """,
        )
        cfg = Config(path)
        assert cfg.check_config() is True
        task = cfg.config["tasks"][0]
        assert task["retries"] == 0
        assert task["timeout"] == 300
        assert task["enabled"] is True

    def test_global_settings_override_defaults(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            settings:
              max_retries: 5
              timeout: 60
            tasks:
              - name: a
                command: "echo"
            """,
        )
        cfg = Config(path)
        assert cfg.check_config() is True
        task = cfg.config["tasks"][0]
        assert task["retries"] == 5
        assert task["timeout"] == 60

    def test_per_task_override_wins(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            settings:
              max_retries: 5
              timeout: 60
            tasks:
              - name: a
                command: "echo"
                retries: 1
                timeout: 10
            """,
        )
        cfg = Config(path)
        assert cfg.check_config() is True
        task = cfg.config["tasks"][0]
        assert task["retries"] == 1
        assert task["timeout"] == 10


class TestTaskFieldValidation:
    def test_invalid_task_retries(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: "echo"
                retries: -1
            """,
        )
        assert Config(path).check_config() is False

    def test_invalid_task_timeout(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: "echo"
                timeout: 0
            """,
        )
        assert Config(path).check_config() is False

    def test_invalid_max_parallel(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: "echo"
                max_parallel: 0
            """,
        )
        assert Config(path).check_config() is False

    def test_invalid_enabled(self, tmp_path):
        path = write_cfg(
            tmp_path,
            """
            project:
              name: Test
            tasks:
              - name: a
                command: "echo"
                enabled: "yes"
            """,
        )
        assert Config(path).check_config() is False
