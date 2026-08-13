"""Tests for project configuration management."""

from pathlib import Path

import pytest

from bibra.backend.config import parse_bool_or_str, parse_int_or_str
from bibra.backend.dummy import DummyBackend
from bibra.config import (
    BackendConfigError,
    ConfigFileNotFoundError,
    ConfigParseError,
    ProjectConfig,
    ProjectRegistry,
)


class TestProjectRegistry:
    """Tests for ProjectRegistry."""

    def test_load_from_toml(self, tmp_path: Path):
        """Test loading projects from a TOML file."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[project1]\nname = "Test Project"\nbackend = "dummy"\n')

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert len(projects) == 1
        assert "project1" in projects
        assert projects["project1"].name == "Test Project"
        assert projects["project1"].backend == "dummy"

    def test_load_multiple_projects(self, tmp_path: Path):
        """Test loading multiple projects from a TOML file."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[proj_a]\nname = "Project A"\nbackend = "dummy"\n\n'
            '[proj_b]\nname = "Project B"\nbackend = "dummy"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert len(projects) == 2
        assert projects["proj_a"].name == "Project A"
        assert projects["proj_b"].name == "Project B"

    def test_env_var_interpolation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that environment variables are interpolated in config values."""
        monkeypatch.setenv("MY_PROJECT_NAME", "Interpolated Name")
        monkeypatch.setenv("MY_ENDPOINT", "http://example.com")

        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "${MY_PROJECT_NAME}"\n'
            'backend = "dummy"\nendpoint = "${MY_ENDPOINT}"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].name == "Interpolated Name"
        assert projects["test_project"].endpoint == "http://example.com"

    def test_missing_env_var_preserved(self, tmp_path: Path):
        """Test that missing env vars preserve the original placeholder."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "${UNDEFINED_VAR}"\nbackend = "dummy"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].name == "${UNDEFINED_VAR}"

    def test_get_backend(self, tmp_path: Path):
        """Test getting a backend instance by project ID."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[test_project]\nname = "Test"\nbackend = "dummy"\n')

        registry = ProjectRegistry(str(config_file))
        registry.load()
        backend = registry.get_backend("test_project")

        assert isinstance(backend, DummyBackend)

    def test_get_backend_unknown_project(self, tmp_path: Path):
        """Test that unknown project raises ValueError."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[test_project]\nname = "Test"\nbackend = "dummy"\n')

        registry = ProjectRegistry(str(config_file))
        registry.load()

        with pytest.raises(ValueError, match="Unknown project: nonexistent"):
            registry.get_backend("nonexistent")

    def test_list_projects(self, tmp_path: Path):
        """Test listing projects."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[proj1]\nname = "Project 1"\nbackend = "dummy"\n\n'
            '[proj2]\nname = "Project 2"\nbackend = "dummy"\n'
        )

        registry = ProjectRegistry(str(config_file))
        registry.load()
        projects = registry.list_projects()

        assert len(projects) == 2
        assert projects[0]["id"] == "proj1"
        assert projects[0]["name"] == "Project 1"
        assert projects[1]["id"] == "proj2"
        assert projects[1]["name"] == "Project 2"

    def test_default_config_path(self, monkeypatch: pytest.MonkeyPatch):
        """Test that default config path is used when no path is provided."""
        monkeypatch.delenv("BIBRA_CONFIG", raising=False)

        registry = ProjectRegistry()
        assert registry._config_path == "projects.toml"

    def test_env_var_config_path(self, monkeypatch: pytest.MonkeyPatch):
        """Test that BIBRA_CONFIG env var sets the config path."""
        monkeypatch.setenv("BIBRA_CONFIG", "/custom/path.toml")

        registry = ProjectRegistry()
        assert registry._config_path == "/custom/path.toml"

    def test_empty_config_path_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """Test that empty config_path falls back to default."""
        monkeypatch.delenv("BIBRA_CONFIG", raising=False)
        registry = ProjectRegistry("")
        assert registry._config_path == "projects.toml"

    def test_whitespace_config_path_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """Test that whitespace-only config_path falls back to default."""
        monkeypatch.delenv("BIBRA_CONFIG", raising=False)
        registry = ProjectRegistry("   ")
        assert registry._config_path == "projects.toml"

    def test_empty_env_var_config_path_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """Test that empty BIBRA_CONFIG env var falls back to default."""
        monkeypatch.setenv("BIBRA_CONFIG", "")
        registry = ProjectRegistry()
        assert registry._config_path == "projects.toml"

    def test_whitespace_env_var_config_path_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that whitespace-only BIBRA_CONFIG env var falls back to default."""
        monkeypatch.setenv("BIBRA_CONFIG", "   ")
        registry = ProjectRegistry()
        assert registry._config_path == "projects.toml"

    def test_default_config_section(self, tmp_path: Path):
        """Test that [defaults] section provides default values for all projects."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[defaults]\napi_key = "default-key"\n\n'
            '[proj_a]\nname = "Project A"\nbackend = "dummy"\n\n'
            '[proj_b]\nname = "Project B"\nbackend = "dummy"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert len(projects) == 2
        assert projects["proj_a"].api_key == "default-key"
        assert projects["proj_b"].api_key == "default-key"

    def test_project_overrides_defaults(self, tmp_path: Path):
        """Test that project-specific values override [defaults] defaults."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[defaults]\napi_key = "default-key"\n\n'
            '[proj_a]\nname = "Project A"\nbackend = "dummy"\n'
            'api_key = "project-a-key"\n\n'
            '[proj_b]\nname = "Project B"\nbackend = "dummy"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["proj_a"].api_key == "project-a-key"
        assert projects["proj_b"].api_key == "default-key"

    def test_defaults_with_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that env var interpolation works on [defaults] defaults."""
        monkeypatch.setenv("DEFAULT_KEY", "interpolated-key")

        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[defaults]\napi_key = "${DEFAULT_KEY}"\n\n'
            '[proj_a]\nname = "Project A"\nbackend = "dummy"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["proj_a"].api_key == "interpolated-key"

    def test_non_string_toml_values(self, tmp_path: Path):
        """Test that non-string TOML values are handled without crashing."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[test_project]\nname = 123\nbackend = "dummy"\n')

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].name == 123

    def test_non_string_default_values(self, tmp_path: Path):
        """Test that non-string default values are passed through unchanged."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            "[defaults]\nmodel = 42\n\n[test_project]\n"
            'name = "Test"\nbackend = "dummy"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].extra["model"] == 42


class TestProjectConfig:
    """Tests for ProjectConfig."""

    def test_defaults(self):
        """Test ProjectConfig with minimal fields."""
        config = ProjectConfig(id="test", name="Test", backend="dummy")
        assert config.id == "test"
        assert config.name == "Test"
        assert config.backend == "dummy"
        assert config.endpoint is None
        assert config.api_key is None
        assert config.extra == {}

    def test_full_config(self):
        """Test ProjectConfig with extra backend-specific options."""
        config = ProjectConfig(
            id="test",
            name="Test",
            backend="nuextract",
            endpoint="http://example.com",
            api_key="secret",
            extra={
                "model": "nuextract3",
                "thinking": True,
                "instructions": "Custom instructions",
                "dpi": 200,
            },
        )
        assert config.endpoint == "http://example.com"
        assert config.api_key == "secret"
        assert config.extra["model"] == "nuextract3"
        assert config.extra["thinking"] is True
        assert config.extra["instructions"] == "Custom instructions"
        assert config.extra["dpi"] == 200

    def test_load_dpi_from_toml(self, tmp_path: Path):
        """Test loading dpi from TOML ends up in extra dict."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\ndpi = 200\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].extra["dpi"] == 200

    def test_load_thinking_from_toml(self, tmp_path: Path):
        """Test loading thinking from TOML ends up in extra dict."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\nthinking = true\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].extra["thinking"] is True

    def test_load_backend_config_with_dpi(self, tmp_path: Path):
        """Test that dpi is passed to backend config via build_config."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\ndpi = 250\n'
        )

        registry = ProjectRegistry(str(config_file))
        registry.load()
        backend = registry.get_backend("test_project")

        assert backend.cfg.dpi == 250

    def test_load_invalid_backend_type(self, tmp_path: Path):
        """Test that load raises BackendConfigError for unknown backend types."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[test_project]\nname = "Test"\nbackend = "foobar"\n')

        registry = ProjectRegistry(str(config_file))

        with pytest.raises(BackendConfigError, match="Unknown backend type: foobar"):
            registry.load()

    def test_load_missing_backend_type(self, tmp_path: Path):
        """Test that load raises BackendConfigError when backend is not specified."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[test_project]\nname = "Test"\n')

        registry = ProjectRegistry(str(config_file))

        with pytest.raises(BackendConfigError, match="Missing backend type"):
            registry.load()

    def test_load_missing_config_file(self, tmp_path: Path):
        """Test that ConfigFileNotFoundError is raised when config file is missing."""
        registry = ProjectRegistry(str(tmp_path / "nonexistent.toml"))

        with pytest.raises(ConfigFileNotFoundError, match="Config file not found"):
            registry.load()

    def test_load_invalid_toml(self, tmp_path: Path):
        """Test that ConfigParseError is raised when TOML is malformed."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text("[invalid\nthis is not valid toml{{{")

        registry = ProjectRegistry(str(config_file))

        with pytest.raises(ConfigParseError, match="Failed to parse"):
            registry.load()

    def test_env_var_interpolation_on_thinking_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that env var interpolation works on thinking string values."""
        monkeypatch.setenv("THINKING_MODE", "true")

        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\nthinking = "${THINKING_MODE}"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].extra["thinking"] == "true"

    def test_env_var_interpolation_on_dpi_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that env var interpolation works on dpi string values."""
        monkeypatch.setenv("DPI_VALUE", "300")

        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\ndpi = "${DPI_VALUE}"\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].extra["dpi"] == "300"

    def test_invalid_extra_keys_raise_backend_config_error(self, tmp_path: Path):
        """Test that unknown extra keys produce a clear BackendConfigError."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            "[test_project]\n"
            'name = "Test"\n'
            'backend = "greylitlm"\n'
            'unknown_key = "bad_value"\n'
        )

        registry = ProjectRegistry(str(config_file))
        registry.load()

        with pytest.raises(BackendConfigError) as exc_info:
            registry.get_backend("test_project")

        error_msg = str(exc_info.value)
        assert "test_project" in error_msg
        assert "greylitlm" in error_msg

    def test_greylitlm_system_prompt_from_toml(self, tmp_path: Path):
        """Test that system_prompt from TOML flows through extra to GreyLitLMConfig."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            "[test_project]\n"
            'name = "Test"\n'
            'backend = "greylitlm"\n'
            'system_prompt = "Custom librarian prompt"\n'
        )

        registry = ProjectRegistry(str(config_file))
        registry.load()
        backend = registry.get_backend("test_project")

        assert backend.cfg.system_prompt == "Custom librarian prompt"

    def test_greylitlm_instructions_from_toml(self, tmp_path: Path):
        """Test that instructions from TOML flows through extra to GreyLitLMConfig."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            "[test_project]\n"
            'name = "Test"\n'
            'backend = "greylitlm"\n'
            'instructions = "Extract authors and year only"\n'
        )

        registry = ProjectRegistry(str(config_file))
        registry.load()
        backend = registry.get_backend("test_project")

        assert backend.cfg.instructions == "Extract authors and year only"


class TestParseBoolOrStr:
    """Tests for parse_bool_or_str validator."""

    def test_bool_true_passed_through(self):
        assert parse_bool_or_str(True) is True

    def test_bool_false_passed_through(self):
        assert parse_bool_or_str(False) is False

    def test_int_zero_returns_false(self):
        assert parse_bool_or_str(0) is False

    def test_int_nonzero_returns_true(self):
        assert parse_bool_or_str(1) is True

    def test_int_nonzero_negative_returns_true(self):
        assert parse_bool_or_str(-1) is True

    def test_string_true_returns_true(self):
        assert parse_bool_or_str("true") is True

    def test_string_1_returns_true(self):
        assert parse_bool_or_str("1") is True

    def test_string_with_whitespace(self):
        assert parse_bool_or_str("  true  ") is True

    def test_string_false_returns_false(self):
        assert parse_bool_or_str("false") is False

    def test_string_0_returns_false(self):
        assert parse_bool_or_str("0") is False

    def test_string_yes_returns_false_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert parse_bool_or_str("yes") is False
        assert "Unrecognized bool value" in caplog.text
        assert "'yes'" in caplog.text

    def test_string_maybe_returns_false_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert parse_bool_or_str("maybe") is False
        assert "Unrecognized bool value" in caplog.text

    def test_string_2_returns_false_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert parse_bool_or_str("2") is False
        assert "Unrecognized bool value" in caplog.text


class TestParseIntOrStr:
    """Tests for parse_int_or_str validator."""

    def test_int_passed_through(self):
        assert parse_int_or_str(42) == 42

    def test_string_number(self):
        assert parse_int_or_str("42") == 42

    def test_string_negative_number(self):
        assert parse_int_or_str("-5") == -5

    def test_string_with_whitespace(self):
        assert parse_int_or_str("  10  ") == 10

    def test_string_invalid_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert parse_int_or_str("abc") == 0
        assert "Unrecognized int value" in caplog.text
        assert "'abc'" in caplog.text

    def test_string_float_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert parse_int_or_str("3.14") == 0
        assert "Unrecognized int value" in caplog.text

    def test_empty_string_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert parse_int_or_str("") == 0
        assert "Unrecognized int value" in caplog.text

    def test_whitespace_only_returns_zero_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ):
        assert parse_int_or_str("   ") == 0
        assert "Unrecognized int value" in caplog.text
