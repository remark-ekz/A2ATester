from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_NAME = "a2a_tester.sqlite3"
DB_SIDE_SUFFIXES = ("", "-wal", "-shm", "-journal")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from a2a_tester.storage.paths import resolve_data_dir  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find and reset A2A Tester local data.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--portable", action="store_true", help="only check portable data directories")
    scope.add_argument("--system", action="store_true", help="only check the OS app-data directory")
    scope.add_argument("--all", action="store_true", help="check portable and OS app-data directories")
    parser.add_argument("--path", action="append", default=[], help="extra database file or data directory to reset")
    parser.add_argument("--scan", action="append", default=[], help="recursively scan a directory for a2a_tester.sqlite3")
    parser.add_argument("--keep-certificates", action="store_true", help="delete only SQLite files, keep copied certificates")
    parser.add_argument("--yes", action="store_true", help="actually delete files; without this flag the script is dry-run")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    include_certificates = not args.keep_certificates
    candidates = collect_candidate_dirs(args)
    targets = collect_targets(candidates, args.path, args.scan, include_certificates)

    print_checked_locations(candidates, args.path, args.scan)
    if not targets:
        print("Nothing to remove.")
        return 0

    print()
    print("Targets:")
    for target in targets:
        kind = "dir " if target.is_dir() else "file"
        print(f"  {kind} {target}")

    if not args.yes:
        print()
        print("Dry-run only. Re-run with --yes to delete these targets.")
        return 0

    failures = delete_targets(targets)
    if failures:
        print()
        print("Some targets were not removed:")
        for target, error in failures:
            print(f"  {target}: {error}")
        return 1

    print()
    print("A2A Tester local data reset complete.")
    return 0


def collect_candidate_dirs(args: argparse.Namespace) -> list[Path]:
    include_portable = args.all or not (args.portable or args.system) or args.portable
    include_system = args.all or not (args.portable or args.system) or args.system

    candidates: list[Path] = []
    if include_portable:
        candidates.append(PROJECT_ROOT / "data")
        cwd_data = Path.cwd() / "data"
        if cwd_data.resolve() != (PROJECT_ROOT / "data").resolve():
            candidates.append(cwd_data)
    if include_system:
        candidates.append(resolve_data_dir(portable=False))
    return unique_paths(candidates)


def collect_targets(candidate_dirs: list[Path], extra_paths: list[str], scan_roots: list[str], include_certificates: bool) -> list[Path]:
    targets: list[Path] = []

    for data_dir in candidate_dirs:
        targets.extend(targets_for_data_dir(data_dir, include_certificates))

    for raw_path in extra_paths:
        targets.extend(targets_for_custom_path(Path(raw_path).expanduser(), include_certificates))

    for raw_root in scan_roots:
        root = Path(raw_root).expanduser()
        targets.extend(targets_for_scan(root, include_certificates))

    return [path for path in unique_paths(targets) if path.exists()]


def targets_for_data_dir(data_dir: Path, include_certificates: bool) -> list[Path]:
    targets = [data_dir / f"{DB_NAME}{suffix}" for suffix in DB_SIDE_SUFFIXES]
    if include_certificates:
        targets.append(data_dir / "certificates")
    return targets


def targets_for_custom_path(path: Path, include_certificates: bool) -> list[Path]:
    if path.suffix in {".sqlite", ".sqlite3", ".db"} or path.name == DB_NAME:
        targets = [path.with_name(f"{path.name}{suffix}") for suffix in DB_SIDE_SUFFIXES]
        if include_certificates:
            targets.append(path.parent / "certificates")
        return targets
    return targets_for_data_dir(path, include_certificates)


def targets_for_scan(root: Path, include_certificates: bool) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return targets_for_custom_path(root, include_certificates)

    targets: list[Path] = []
    for db_file in safe_rglob(root, DB_NAME):
        targets.extend(targets_for_custom_path(db_file, include_certificates=False))
        if include_certificates:
            certificates_dir = db_file.parent / "certificates"
            if certificates_dir.exists():
                targets.append(certificates_dir)
    return targets


def safe_rglob(root: Path, pattern: str) -> list[Path]:
    found: list[Path] = []
    try:
        iterator = root.rglob(pattern)
        for path in iterator:
            found.append(path)
    except OSError as error:
        print(f"Could not scan {root}: {error}")
    return found


def delete_targets(targets: list[Path]) -> list[tuple[Path, str]]:
    failures: list[tuple[Path, str]] = []
    for target in sorted(targets, key=lambda item: len(item.parts), reverse=True):
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as error:
            failures.append((target, str(error)))
    return failures


def print_checked_locations(candidate_dirs: list[Path], extra_paths: list[str], scan_roots: list[str]) -> None:
    print("Checked data directories:")
    for path in candidate_dirs:
        print(f"  {path}")
    if extra_paths:
        print("Extra paths:")
        for path in extra_paths:
            print(f"  {Path(path).expanduser()}")
    if scan_roots:
        print("Scan roots:")
        for path in scan_roots:
            print(f"  {Path(path).expanduser()}")


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


if __name__ == "__main__":
    raise SystemExit(main())
