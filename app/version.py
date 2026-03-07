"""Read application version from pyproject.toml."""

import tomllib
from pathlib import Path

_pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"


def get_version() -> str:
    try:
        with open(_pyproject, "rb") as f:
            data = tomllib.load(f)
        return data["project"]["version"]
    except Exception:
        return "0.0.0-unknown"


VERSION = get_version()
