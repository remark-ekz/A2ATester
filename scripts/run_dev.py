from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from uv_environment import uv_environment


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def local_project_python() -> Path | None:
    scripts_dir = "Scripts" if sys.platform == "win32" else "bin"
    executable = "python.exe" if sys.platform == "win32" else "python"
    candidate = PROJECT_ROOT / ".venv" / scripts_dir / executable
    if not candidate.is_file():
        return None
    probe = subprocess.run(
        [str(candidate), "-c", "import fastapi, httpx, uvicorn, webview"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return candidate if probe.returncode == 0 else None


def run(command: list[str], *, environment: dict[str, str] | None = None) -> int:
    try:
        return subprocess.call(command, cwd=PROJECT_ROOT, env=environment)
    except KeyboardInterrupt:
        return 130


def main(argv: list[str] | None = None) -> int:
    arguments = argv or sys.argv[1:]
    python = local_project_python()
    if python:
        command = [str(python), "-u", "-m", "a2a_tester.main", *arguments]
        return run(command)

    uv = shutil.which("uv")
    if not uv:
        print("Dependencies are missing. Run 'uv sync' to create .venv.", file=sys.stderr)
        return 1
    command = [uv, "run", "python", "-u", "-m", "a2a_tester.main", *arguments]
    return run(command, environment=uv_environment())


if __name__ == "__main__":
    raise SystemExit(main())
