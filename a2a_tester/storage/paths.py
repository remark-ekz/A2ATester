from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "A2A Tester"


def executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def resolve_data_dir(portable: bool = False) -> Path:
    if portable:
        return executable_dir() / "data"

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    return base / APP_DIR_NAME
