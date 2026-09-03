"""Reasonhound: AI-assisted security scanner that reasons like a senior researcher."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("reasonhound")
except PackageNotFoundError:  # pragma: no cover - only when running from a raw checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
