from __future__ import annotations

import os
import sys
from pathlib import Path


def uv_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("UV_PROJECT_ENVIRONMENT", str(external_venv_path()))
    return environment


def external_venv_path() -> Path:
    configured = os.environ.get("A2A_TESTER_VENV")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "A2ATester" / "venv"
    return Path.home() / ".cache" / "a2a-tester" / "venv"
