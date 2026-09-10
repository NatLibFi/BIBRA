"""Project configuration management for BIBRA.

This module provides project configuration loading from TOML files,
with support for environment variable interpolation.
"""

import logging
import importlib
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bibra.backend import BaseBackend

logger = logging.getLogger(__name__)


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


# Sentinel value for BIBRA_URL_PROXY meaning "fetch directly, with the
# full in-app URL validation". Any other non-blank value is treated as a
# proxy URL; a blank/unset value means URL fetching is refused entirely.
URL_FETCH_DIRECT = "direct"

# Defaults for the URL fetch policy (BIBRA_URL_* env vars).
DEFAULT_URL_SCHEMES: list[str] = ["https"]
DEFAULT_URL_CONTENT_TYPES: list[str] = ["application/pdf"]
DEFAULT_URL_MAX_BYTES: int = 50 * 1024 * 1024  # 50 MiB
DEFAULT_URL_TIMEOUT: float = 30.0  # seconds
DEFAULT_URL_MAX_REDIRECTS: int = 5
DEFAULT_URL_ALLOW_IP_HOSTS: bool = False


@dataclass(frozen=True)
class UrlFetchPolicy:
    """Policy governing how BIBRA fetches user-supplied URLs (SSRF hardening).

    Attributes:
        proxy: The egress proxy URL, the literal sentinel "direct" (see
            URL_FETCH_DIRECT) for direct egress, or None to refuse fetching.
        schemes: Allowed URL schemes (e.g. ["https"]).
        content_types: Allowed response content types (MIME, no parameters).
        max_bytes: Hard cap on total downloaded bytes.
        timeout: Seconds for connect/read/write/pool timeouts.
        max_redirects: Maximum number of redirect hops; every hop is
            re-validated against the policy.
        allow_ip_hosts: Whether URLs whose host is an IP literal are allowed.
    """

    proxy: str | None
    schemes: tuple[str, ...]
    content_types: tuple[str, ...]
    max_bytes: int
    timeout: float
    max_redirects: int
    allow_ip_hosts: bool

    @property
    def proxy_required(self) -> bool:
        """True when URL fetching must be refused (no proxy or direct set)."""
        return self.proxy is None


def _parse_list_env(name: str, default: list[str]) -> tuple[str, ...]:
    """Parse a comma-separated env var into a tuple of stripped strings.

    Falls back to the default when the variable is unset or blank.
    """
    raw = os.environ.get(name, "")
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return tuple(items) if items else tuple(item.lower() for item in default)


def _parse_int_env(name: str, default: int) -> int:
    """Parse a positive-integer env var, falling back to the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.debug("Invalid %s=%r; using default %d", name, raw, default)
        return default
    return value if value > 0 else default


def _parse_float_env(name: str, default: float) -> float:
    """Parse a positive-float env var, falling back to the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.debug("Invalid %s=%r; using default %f", name, raw, default)
        return default
    return value if value > 0 else default


def _parse_bool_env(name: str, default: bool) -> bool:
    """Parse a boolean env var (1/true/yes/on), falling back to the default."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def get_url_proxy() -> str | None:
    """Return the BIBRA_URL_PROXY environment variable value.

    Blank or whitespace-only values are normalized to None, so that
    callers can safely pass the result to httpx proxy arguments.

    Returns:
        The proxy URL string, or None if not set or blank.
    """
    proxy = os.environ.get("BIBRA_URL_PROXY")
    return proxy.strip() if proxy and proxy.strip() else None


def load_url_fetch_policy(cli_fallback: bool = False) -> UrlFetchPolicy:
    """Build a UrlFetchPolicy from the BIBRA_URL_* environment variables.

    Semantics of BIBRA_URL_PROXY:
      - unset/blank: URL fetching is refused (proxy_required is True)
      - "direct": direct egress is allowed, subject to full in-app validation
      - anything else: used as the egress proxy URL

    With ``cli_fallback=True`` (the CLI's intent), an unset/blank
    BIBRA_URL_PROXY is treated as "direct" instead of refusing: the CLI
    is a local tool and falls back to direct egress with full in-app
    validation, while the REST API keeps refusing by default.

    Invalid numeric/boolean values are logged and replaced by their
    defaults, so that a misconfigured setting never crashes the app.
    """
    proxy = get_url_proxy()
    if proxy is None and cli_fallback:
        proxy = URL_FETCH_DIRECT
    return UrlFetchPolicy(
        proxy=proxy,
        schemes=_parse_list_env("BIBRA_URL_SCHEMES", DEFAULT_URL_SCHEMES),
        content_types=_parse_list_env(
            "BIBRA_URL_CONTENT_TYPES", DEFAULT_URL_CONTENT_TYPES
        ),
        max_bytes=_parse_int_env("BIBRA_URL_MAX_BYTES", DEFAULT_URL_MAX_BYTES),
        timeout=_parse_float_env("BIBRA_URL_TIMEOUT", DEFAULT_URL_TIMEOUT),
        max_redirects=_parse_int_env(
            "BIBRA_URL_MAX_REDIRECTS", DEFAULT_URL_MAX_REDIRECTS
        ),
        allow_ip_hosts=_parse_bool_env(
            "BIBRA_URL_ALLOW_IP_HOSTS", DEFAULT_URL_ALLOW_IP_HOSTS
        ),
    )
