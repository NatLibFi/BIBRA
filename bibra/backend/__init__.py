import importlib
from typing import Any

_LAZY_MODULES: dict[str, list[str]] = {
    "bibra.backend.base": ["BaseBackend"],
    "bibra.backend.config": ["GlobalLLMConfig"],
    "bibra.backend.dummy": ["DummyBackend"],
    "bibra.backend.greylitlm": ["GreyLitLMBackend", "GreyLitLMConfig"],
    "bibra.backend.nuextract": ["NuExtractBackend", "NuExtractConfig"],
}

# Derived from _LAZY_MODULES to avoid duplication of the names
__all__ = [name for names in _LAZY_MODULES.values() for name in names]


def __getattr__(name: str) -> Any:
    """Import and return a lazily re-exported backend name on access."""
    for module, names in _LAZY_MODULES.items():
        if name in names:
            return getattr(importlib.import_module(module), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
