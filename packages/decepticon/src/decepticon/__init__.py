"""Decepticon — AI-powered autonomous red team testing framework."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from decepticon import _boot, compat

try:
    # pyproject.toml carries a "0.0.0" sentinel; release.yml stamps the
    # real tag into the package metadata at Docker build time, and
    # importlib.metadata reads it back here. Local checkouts read 0.0.0.
    __version__ = _version("decepticon")
except PackageNotFoundError:
    __version__ = "0.0.0"

__package_name__ = "decepticon"

# Phase 2 framework boot — register OSS roles with RoleRegistry,
# materialize the PluginRegistry singleton, and surface the legacy
# import paths via the compat shim. All idempotent / opt-out via env.
_boot.run()
compat.register_legacy_imports()
