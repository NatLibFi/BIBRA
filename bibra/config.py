"""Project configuration management for BIBRA.

This module provides project configuration loading from TOML files,
with support for environment variable interpolation.
"""

import importlib
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bibra.backend.base import BaseBackend


class ConfigError(Exception):
    """Base exception for project configuration errors."""

    description: str = "Configuration error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.description)
        if message is not None:
            self.description = message


class ConfigFileNotFoundError(ConfigError):
    """Raised when the configuration file cannot be found."""

    description = "Configuration file not found"


class ConfigParseError(ConfigError):
    """Raised when the configuration file cannot be parsed."""

    description = "Configuration file is malformed"


class ProjectNotFoundError(ValueError):
    """Raised when a project ID is not found in the registry."""


class BackendConfigError(ConfigError):
    """Raised when a project's backend configuration is invalid."""

    description = "Invalid backend configuration"


# Map of backend type -> "module.ClassName" import path.
_BACKEND_MAP: dict[str, str] = {
    "dummy": "bibra.backend.dummy:DummyBackend",
    "greylitlm": "bibra.backend.greylitlm:GreyLitLMBackend",
    "nuextract": "bibra.backend.nuextract:NuExtractBackend",
}


def _get_backend_class(backend_type: str) -> type[BaseBackend] | None:
    """Import and return the backend class for the given backend type.

    Backend modules are imported on demand (and cached by Python's
    import machinery) to keep CLI startup fast.
    """
    if backend_type not in _BACKEND_MAP:
        return None
    import_path = _BACKEND_MAP.get(backend_type)
    module_path, class_name = import_path.split(":", 1)
    return getattr(importlib.import_module(module_path), class_name)


# Keys recognized as global/project-level metadata.
# All other keys are passed as-is into the backend-specific ``extra`` dict.
_GLOBAL_KEYS = {"name", "backend", "endpoint", "api_key"}


@dataclass
class ProjectConfig:
    """Configuration for a single project.

    Attributes:
        id: Unique project identifier.
        name: Human-readable project name.
        backend: Backend type identifier (e.g. "dummy", "greylitlm", "nuextract").
        endpoint: LLM endpoint URL.
        api_key: API key for authentication.
        extra: Backend-specific options passed to the backend's config schema.
    """

    id: str
    name: str
    backend: str
    endpoint: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _interpolate_env_vars(value: Any) -> Any:
    """Interpolate environment variables in a string value.

    Supports ${VAR_NAME} syntax. If the environment variable is not set,
    the original placeholder is preserved.

    Args:
        value: The string value to interpolate.

    Returns:
        The interpolated string, or the input unchanged if non-string.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    result = value
    start = 0
    while start < len(result):
        open_pos = result.find("${", start)
        if open_pos == -1:
            break
        close_pos = result.find("}", open_pos + 2)
        if close_pos == -1:
            break

        var_name = result[open_pos + 2 : close_pos]
        env_value = os.environ.get(var_name)
        if env_value is not None:
            result = result[:open_pos] + env_value + result[close_pos + 1 :]
            start = open_pos + len(env_value)
        else:
            start = close_pos + 1

    return result


def _interpolate_dict_values(d: dict[str, Any]) -> dict[str, Any]:
    """Interpolate environment variables in all string values of a dict."""
    return {
        key: _interpolate_env_vars(value) if isinstance(value, str) else value
        for key, value in d.items()
    }


class ProjectRegistry:
    """Loads and manages project configurations from a TOML file.

    The registry reads projects from a TOML file and provides methods
    to instantiate backends and list configured projects.

    Attributes:
        config_path: Path to the TOML configuration file.
    """

    def __init__(self, config_path: str | None = None):
        """Initialize the project registry.

        Args:
            config_path: Path to the TOML config file. Defaults to
                BIBRA_CONFIG env var or "projects.toml".
        """
        raw_path = config_path or os.environ.get("BIBRA_CONFIG")
        self._config_path = (
            raw_path.strip() if raw_path and raw_path.strip() else "projects.toml"
        )
        self._projects: dict[str, ProjectConfig] = {}

    def load(self) -> dict[str, ProjectConfig]:
        """Load and parse the TOML configuration file.

        Returns:
            Dictionary mapping project IDs to ProjectConfig objects.

        Raises:
            ConfigFileNotFoundError: If the config file does not exist.
            ConfigParseError: If the config file cannot be parsed.
            BackendConfigError: If a backend type is not recognized.
        """
        path = Path(self._config_path)
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            raise ConfigFileNotFoundError(f"Config file not found: {path}") from None
        except tomllib.TOMLDecodeError as e:
            raise ConfigParseError(
                f"Failed to parse config file '{path}': {e}"
            ) from None

        # Extract defaults from [defaults] section
        defaults: dict[str, Any] = {}
        raw_defaults = data.get("defaults")
        if isinstance(raw_defaults, dict):
            for key, value in raw_defaults.items():
                if isinstance(value, str):
                    defaults[key] = _interpolate_env_vars(value)
                else:
                    defaults[key] = value

        projects: dict[str, ProjectConfig] = {}
        for project_id, config in data.items():
            # Skip non-project sections and defaults section ([defaults])
            if project_id == "defaults" or not isinstance(config, dict):
                continue

            # Merge defaults with project config (project values override)
            merged: dict[str, Any] = dict(defaults)
            merged.update(config)
            # Interpolate all string values in merged
            merged = _interpolate_dict_values(merged)

            backend_type = merged.get("backend")
            if backend_type is None:
                raise BackendConfigError(
                    f"Missing backend type for project '{project_id}'"
                )
            if backend_type not in _BACKEND_MAP:
                raise BackendConfigError(
                    f"Unknown backend type '{backend_type}' for project '{project_id}'"
                )

            # Separate global fields from backend-specific extra fields
            project = ProjectConfig(
                id=project_id,
                name=(
                    str(merged["name"])
                    if merged.get("name") is not None
                    else project_id
                ),
                backend=backend_type,
                endpoint=merged.get("endpoint"),
                api_key=merged.get("api_key"),
                extra={k: v for k, v in merged.items() if k not in _GLOBAL_KEYS},
            )

            projects[project_id] = project

        self._projects = projects
        return projects

    def get_backend(self, project_id: str) -> BaseBackend:
        """Get a configured backend instance for the given project.

        Args:
            project_id: The project identifier.

        Returns:
            A configured backend instance.

        Raises:
            ProjectNotFoundError: If the project is not found.
            BackendConfigError: If the backend configuration is invalid.
        """
        if not self._projects:
            self.load()

        project = self._projects.get(project_id)
        if project is None:
            raise ProjectNotFoundError(f"Unknown project: {project_id}")

        backend_class = _get_backend_class(project.backend)
        if backend_class is None:
            raise BackendConfigError(
                f"Unknown backend type for project '{project_id}': {project.backend}"
            )

        try:
            kwargs = backend_class.build_config(project)
        except ValidationError as e:
            raise BackendConfigError(
                f"Invalid backend config for project '{project_id}' "
                f"(backend: {project.backend}): {e}"
            ) from e
        return backend_class(**kwargs)

    def list_projects(self) -> list[dict[str, Any]]:
        """List all configured projects.

        Returns:
            List of project info dictionaries.
        """
        if not self._projects:
            self.load()

        return [
            {
                "id": project.id,
                "name": project.name,
                "description": f"Project using {project.backend} backend",
            }
            for project in self._projects.values()
        ]
