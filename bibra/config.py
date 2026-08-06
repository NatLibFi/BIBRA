"""Project configuration management for BIBRA.

This module provides project configuration loading from TOML files,
with support for environment variable interpolation.
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bibra.backend.base import BaseBackend
from bibra.backend.config import (
    GlobalLLMConfig,
    GreyLitLMConfig,
    NuExtractConfig,
)
from bibra.backend.dummy import DummyBackend
from bibra.backend.greylitlm import GreyLitLMBackend
from bibra.backend.nuextract import NuExtractBackend

_BACKEND_MAP: dict[str, type[BaseBackend]] = {
    "dummy": DummyBackend,
    "greylitlm": GreyLitLMBackend,
    "nuextract": NuExtractBackend,
}


@dataclass
class ProjectConfig:
    """Configuration for a single project.

    Attributes:
        id: Unique project identifier.
        name: Human-readable project name.
        backend: Backend type identifier (e.g. "dummy", "greylitlm", "nuextract").
        endpoint: LLM endpoint URL.
        api_key: API key for authentication.
        model: Model name for the backend.
        thinking: Enable thinking mode (NuExtract only).
        instructions: Custom instructions for the backend.
        system_prompt: System prompt (GreyLitLM only).
        dpi: DPI for PDF-to-image conversion (NuExtract only).
    """

    id: str
    name: str
    backend: str
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None
    thinking: bool | None = None
    instructions: str | None = None
    system_prompt: str | None = None
    dpi: int | None = None


def _interpolate_env_vars(value: str | None) -> str | None:
    """Interpolate environment variables in a string value.

    Supports ${VAR_NAME} syntax. If the environment variable is not set,
    the original placeholder is preserved.

    Args:
        value: The string value to interpolate.

    Returns:
        The interpolated string, or None if input was None.
    """
    if value is None:
        return None

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


def _parse_bool(value: str | None, default: bool) -> bool:
    """Parse a boolean from a string value.

    Args:
        value: The string to parse.
        default: Default value if input is None.

    Returns:
        Parsed boolean value.
    """
    if value is None:
        return default
    return value.strip().lower() in ("1", "true")


def _build_backend_config(project: ProjectConfig) -> dict[str, Any]:
    """Build backend configuration kwargs from a ProjectConfig.

    Args:
        project: The project configuration.

    Returns:
        Dict of kwargs suitable for backend constructors.
    """
    global_cfg = GlobalLLMConfig(
        endpoint_url=project.endpoint,
        api_key=project.api_key,
    )

    if project.backend == "greylitlm":
        return {
            "global_cfg": global_cfg,
            "greylitlm_cfg": GreyLitLMConfig(
                model=project.model,
                system_prompt=project.system_prompt,
                instructions=project.instructions,
            ),
        }
    elif project.backend == "nuextract":
        return {
            "global_cfg": global_cfg,
            "nuextract_cfg": NuExtractConfig(
                model=project.model,
                thinking=project.thinking,
                instructions=project.instructions,
                dpi=project.dpi,
            ),
        }
    elif project.backend == "dummy":
        return {}
    else:
        raise ValueError(f"Unknown backend type: {project.backend}")


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
        self._config_path = config_path or os.environ.get(
            "BIBRA_CONFIG", "projects.toml"
        )
        self._projects: dict[str, ProjectConfig] = {}

    def load(self) -> dict[str, ProjectConfig]:
        """Load and parse the TOML configuration file.

        Returns:
            Dictionary mapping project IDs to ProjectConfig objects.

        Raises:
            FileNotFoundError: If the config file does not exist.
            ValueError: If a backend type is not recognized.
        """
        path = Path(self._config_path)
        with open(path, "rb") as f:
            data = tomllib.load(f)

        projects: dict[str, ProjectConfig] = {}
        for project_id, config in data.items():
            # Skip non-project sections and defaults section ([*])
            if project_id == "*" or not isinstance(config, dict):
                continue

            # Interpolate environment variables in string values
            raw_name = _interpolate_env_vars(config.get("name"))
            raw_endpoint = _interpolate_env_vars(config.get("endpoint"))
            raw_api_key = _interpolate_env_vars(config.get("api_key"))
            raw_model = _interpolate_env_vars(config.get("model"))
            raw_instructions = _interpolate_env_vars(config.get("instructions"))
            raw_system_prompt = _interpolate_env_vars(config.get("system_prompt"))

            # Parse thinking as boolean string if present
            thinking_raw = config.get("thinking")
            if isinstance(thinking_raw, str):
                thinking = _parse_bool(thinking_raw, default=False)
            elif isinstance(thinking_raw, bool):
                thinking = thinking_raw
            else:
                thinking = None

            # Parse dpi as integer if present
            dpi_raw = config.get("dpi")
            if isinstance(dpi_raw, int):
                dpi = dpi_raw
            elif isinstance(dpi_raw, str):
                try:
                    parsed = int(dpi_raw.strip())
                    dpi = parsed if parsed > 0 else None
                except (ValueError, TypeError):
                    dpi = None
            else:
                dpi = None

            backend_type = config.get("backend")
            if backend_type is None:
                raise ValueError(f"Missing backend type for project '{project_id}'")
            if backend_type not in _BACKEND_MAP:
                raise ValueError(f"Unknown backend type: {backend_type}")

            project = ProjectConfig(
                id=project_id,
                name=raw_name or project_id,
                backend=backend_type,
                endpoint=raw_endpoint,
                api_key=raw_api_key,
                model=raw_model,
                thinking=thinking,
                instructions=raw_instructions,
                system_prompt=raw_system_prompt,
                dpi=dpi,
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
            ValueError: If the project is not found or backend is unknown.
        """
        if not self._projects:
            self.load()

        project = self._projects.get(project_id)
        if project is None:
            raise ValueError(f"Unknown project: {project_id}")

        backend_class = _BACKEND_MAP.get(project.backend)
        if backend_class is None:
            raise ValueError(
                f"Unknown backend type for project '{project_id}': {project.backend}"
            )

        kwargs = _build_backend_config(project)
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
