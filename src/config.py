"""Configuration loader for the daily SAP job alert system.

Priority: defaults < config.yaml < environment variables (JOBALERT_*).
PyYAML is optional; a small built-in parser handles the example config
well enough, and falls back gracefully if it cannot parse something.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
RESUME_PATH = APP_DIR / "resume.txt"
STATE_PATH = DATA_DIR / "seen_jobs.json"
SAMPLE_JOBS_PATH = APP_DIR / "sample_jobs.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "sources": {
        "demo": {"enabled": True},
        "rapidapi": {"enabled": False, "api_key": "", "engine": "jsearch"},
        "rss_feeds": {"enabled": False, "urls": []},
    },
    "search_queries": [
        "SAP CDS Views AMDP",
        "SAP Embedded Analytics",
        "SAP Datasphere",
        "ABAP CDS",
        "HANA Calculation View",
        "SAP Fiori analytical app",
    ],
    "preferred_locations": ["Pune", "India", "Remote", "Work from home", "WFH"],
    "experience_years": "3+",
    "scoring": {
        "skill_weight": 0.5,
        "title_weight": 0.3,
        "location_weight": 0.15,
        "recency_weight": 0.05,
        "relevant_threshold": 0.60,
        "maybe_threshold": 0.40,
    },
    "notifications": {
        "console": True,
        "email": {
            "enabled": False,
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_pass": "",
            "to": "",
        },
        "windows_toast": True,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Tiny YAML subset parser: nested maps via indentation, scalars, lists."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    pending_key: str | None = None
    pending_list: list[str] | None = None

    def flush_pending() -> None:
        nonlocal pending_key, pending_list
        # Only assign a pending list when we actually collected list items.
        # An empty pending_list means the key already got a nested dict.
        if pending_key is not None and pending_list:
            for _, d in reversed(stack):
                if pending_key in d:
                    d[pending_key] = pending_list
                    break
        pending_key = None
        pending_list = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        line = raw_line.strip()

        # Strip inline comments (not inside quotes, good enough for this config)
        if " #" in line:
            line = line[: line.index(" #")].rstrip()

        if line.startswith("- "):
            if pending_list is not None:
                item = line[2:].strip().strip('"').strip("'")
                pending_list.append(item)
            continue

        flush_pending()

        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if value == "":
            # could be a mapping or a list; handle next lines
            new_dict: dict[str, Any] = {}
            current[key] = new_dict
            stack.append((indent, new_dict))
            pending_key = key
            pending_list = []
        else:
            current[key] = _coerce(value)

    flush_pending()
    return root


def _coerce(value: str) -> Any:
    if value == "true":
        return True
    if value == "false":
        return False
    if value in ("", '""', "''"):
        return ""
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value.strip('"').strip("'")


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (no overwrite)."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(config_path: Path | str | None = None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)

    # Load .env so JOBALERT_* secrets there are available as env overrides.
    _load_env_file(APP_DIR / ".env")

    path = Path(config_path) if config_path else APP_DIR / "config.yaml"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore

            parsed = yaml.safe_load(text) or {}
        except ImportError:
            parsed = _parse_simple_yaml(text)
        if isinstance(parsed, dict):
            config = _deep_merge(config, parsed)

    # Environment overrides: JOBALERT_SOURCES__RAPIDAPI__API_KEY, etc.
    prefix = "JOBALERT_"
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        parts = [p.lower() for p in env_key[len(prefix) :].split("__")]
        if not parts:
            continue
        target = config
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        # coerce booleans/numbers
        if env_value.lower() in ("true", "false"):
            env_value_typed: Any = env_value.lower() == "true"
        else:
            try:
                env_value_typed = int(env_value)
            except ValueError:
                try:
                    env_value_typed = float(env_value)
                except ValueError:
                    env_value_typed = env_value
        target[parts[-1]] = env_value_typed

    return config


@dataclass
class AppConfig:
    sources: dict[str, Any]
    search_queries: list[str]
    preferred_locations: list[str]
    experience_years: str
    scoring: dict[str, Any]
    notifications: dict[str, Any]

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "AppConfig":
        return cls(
            sources=config.get("sources", {}),
            search_queries=config.get("search_queries", []),
            preferred_locations=config.get("preferred_locations", []),
            experience_years=config.get("experience_years", ""),
            scoring=config.get("scoring", {}),
            notifications=config.get("notifications", {}),
        )
