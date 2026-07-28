from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from uv_environment import uv_environment


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def local_python_with_pyinstaller() -> Path | None:
    candidates = [
        Path(sys.executable),
        PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"),
    ]
    checked: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.absolute()
        if candidate in checked or not candidate.is_file():
            continue
        checked.add(candidate)
        probe = subprocess.run(
            [str(candidate), "-c", "import PyInstaller"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build A2A Tester with PyInstaller")
    parser.add_argument(
        "--app",
        action="store_true",
        help="build a macOS/Windows windowed app bundle instead of a single executable",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = uv_environment()
    env.setdefault("PYINSTALLER_CONFIG_DIR", str(PROJECT_ROOT / ".pyinstaller"))
    data_separator = ";" if sys.platform == "win32" else ":"
    frontend_data = f"{PROJECT_ROOT / 'a2a_tester' / 'frontend'}{data_separator}a2a_tester/frontend"

    pyinstaller_command = [
        "--noconfirm",
        "--clean",
        "--add-data",
        frontend_data,
        "--name",
        "A2ATester",
    ]
    if args.app:
        pyinstaller_command.append("--windowed")
    else:
        pyinstaller_command.append("--onefile")
        if sys.platform != "darwin":
            pyinstaller_command.append("--windowed")
    pyinstaller_command.append(str(PROJECT_ROOT / "a2a_tester" / "main.py"))

    local_python = local_python_with_pyinstaller()
    uv = None
    if local_python:
        command = [str(local_python), "-m", "PyInstaller", *pyinstaller_command]
    else:
        uv = shutil.which("uv")
    if not local_python and uv:
        command = [uv, "run", "--extra", "build", "python", "-m", "PyInstaller", *pyinstaller_command]
    elif not local_python:
        command = [sys.executable, "-m", "PyInstaller", *pyinstaller_command]
    return subprocess.call(command, cwd=PROJECT_ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
