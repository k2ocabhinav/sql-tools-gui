"""Load local schema and workfile defaults without requiring private settings."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PUBLIC_SCHEMA_DEFAULTS = [f"schema_{letter}" for letter in "abcdefg"]
PUBLIC_DEVELOPER_NAME = "Developer"
PUBLIC_TEMP_PREFIX = "temp_"
_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,63}$")
_TEMP_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,31}$")


def load_private_settings() -> dict:
    """Return local or bundled release settings without requiring private data."""
    configured_path = os.environ.get("SQL_TOOLS_PRIVATE_CONFIG", "").strip()
    if configured_path:
        candidates = [Path(configured_path).expanduser()]
    elif getattr(sys, "frozen", False):
        candidates = [
            Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            / "generated" / "build_profile.json"
        ]
    else:
        candidates = [Path(__file__).resolve().parents[1] / ".sqltools-private.json"]
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def schema_code(schema: str) -> str:
    """Reduce a configured schema name to its short environment suffix."""
    configured_prefix = load_private_settings().get("schema_prefix", "schema_")
    if isinstance(configured_prefix, str) and configured_prefix and schema.startswith(configured_prefix):
        return schema[len(configured_prefix):]
    # Parse legacy prefixed names without embedding any site-specific identifier.
    legacy = re.match(r"^db_[A-Za-z0-9]+_(.+)$", schema)
    return legacy.group(1) if legacy else schema


def default_schemas() -> list[str]:
    configured = load_private_settings().get("default_schemas")
    if not isinstance(configured, list) or not configured:
        return list(PUBLIC_SCHEMA_DEFAULTS)
    names = [str(item).strip() for item in configured]
    if len(names) > 64 or any(not _SCHEMA_NAME.fullmatch(name) for name in names):
        return list(PUBLIC_SCHEMA_DEFAULTS)
    if len(names) != len(set(names)):
        return list(PUBLIC_SCHEMA_DEFAULTS)
    return names


def profile_schemas(*, public: bool) -> list[str]:
    """Return the schema defaults to embed in a local or shareable build."""
    return list(PUBLIC_SCHEMA_DEFAULTS) if public else default_schemas()


def default_developer_name() -> str:
    """Return a safe local workfile author label or the generic public default."""
    configured = load_private_settings().get("developer_name")
    if not isinstance(configured, str):
        return PUBLIC_DEVELOPER_NAME
    name = configured.strip()
    if not name or len(name) > 80 or any(
        ord(character) < 32 or ord(character) == 127 for character in name
    ):
        return PUBLIC_DEVELOPER_NAME
    return name


def default_temp_prefix() -> str:
    """Return a validated local temporary-object prefix."""
    configured = load_private_settings().get("temp_prefix")
    if not isinstance(configured, str) or not _TEMP_PREFIX.fullmatch(configured):
        return PUBLIC_TEMP_PREFIX
    return configured


def profile_workfile_defaults(*, public: bool) -> dict[str, str]:
    """Return workfile defaults to embed in a local or shareable build profile."""
    if public:
        return {
            "developer_name": PUBLIC_DEVELOPER_NAME,
            "temp_prefix": PUBLIC_TEMP_PREFIX,
        }
    return {
        "developer_name": default_developer_name(),
        "temp_prefix": default_temp_prefix(),
    }
