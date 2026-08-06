"""Tests for project configuration management."""

from pathlib import Path

import pytest

from bibra.backend.dummy import DummyBackend
from bibra.config import ProjectConfig, ProjectRegistry


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
        assert config.model is None
        assert config.thinking is None
        assert config.instructions is None
        assert config.system_prompt is None
        assert config.dpi is None

    def test_full_config(self):
        """Test ProjectConfig with all fields."""
        config = ProjectConfig(
            id="test",
            name="Test",
            backend="nuextract",
            endpoint="http://example.com",
            api_key="secret",
            model="nuextract3",
            thinking=True,
            instructions="Custom instructions",
            system_prompt="System prompt",
            dpi=200,
        )
        assert config.endpoint == "http://example.com"
        assert config.api_key == "secret"
        assert config.model == "nuextract3"
        assert config.thinking is True
        assert config.instructions == "Custom instructions"
        assert config.system_prompt == "System prompt"
        assert config.dpi == 200

    def test_load_dpi_from_toml(self, tmp_path: Path):
        """Test loading dpi from TOML."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\ndpi = 200\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].dpi == 200

    def test_load_thinking_from_toml(self, tmp_path: Path):
        """Test loading thinking from TOML."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\nthinking = true\n'
        )

        registry = ProjectRegistry(str(config_file))
        projects = registry.load()

        assert projects["test_project"].thinking is True

    def test_load_backend_config_with_dpi(self, tmp_path: Path):
        """Test that dpi is passed to NuExtractConfig."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text(
            '[test_project]\nname = "Test"\nbackend = "nuextract"\n'
            'model = "nuextract3"\ndpi = 250\n'
        )

        registry = ProjectRegistry(str(config_file))
        registry.load()
        backend = registry.get_backend("test_project")

        assert backend.nuextract_cfg.dpi == 250

    def test_load_invalid_backend_type(self, tmp_path: Path):
        """Test that load raises ValueError for unknown backend types."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[test_project]\nname = "Test"\nbackend = "foobar"\n')

        registry = ProjectRegistry(str(config_file))

        with pytest.raises(ValueError, match="Unknown backend type: foobar"):
            registry.load()

    def test_load_missing_backend_type(self, tmp_path: Path):
        """Test that load raises ValueError when backend is not specified."""
        config_file = tmp_path / "projects.toml"
        config_file.write_text('[test_project]\nname = "Test"\n')

        registry = ProjectRegistry(str(config_file))

        with pytest.raises(ValueError, match="Missing backend type"):
            registry.load()
