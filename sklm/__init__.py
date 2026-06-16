"""Sklm — Skills manager for AI agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sklm")
except PackageNotFoundError:
    __version__ = "0.0.0"
