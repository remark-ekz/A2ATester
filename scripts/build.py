from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


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
    env = os.environ.copy()
    env.setdefault("PYINSTALLER_CONFIG_DIR", str(Path(".pyinstaller").resolve()))
    data_separator = ";" if sys.platform == "win32" else ":"
    frontend_data = f"a2a_tester/frontend{data_separator}a2a_tester/frontend"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--add-data",
        frontend_data,
        "--name",
        "A2ATester",
    ]
    if args.app:
        command.append("--windowed")
    else:
        command.append("--onefile")
        if sys.platform != "darwin":
            command.append("--windowed")
    command.append("a2a_tester/main.py")
    return subprocess.call(command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
