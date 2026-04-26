from __future__ import annotations

import argparse
import sys

from a2a_tester.storage.database import Database
from a2a_tester.storage.paths import resolve_data_dir
from a2a_tester.server import create_app, run_desktop_app


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A2A Tester")
    parser.add_argument(
        "--portable",
        action="store_true",
        help="store the SQLite database and artifacts next to the executable",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="initialize storage and the API app, then exit without launching the server",
    )
    parser.add_argument("--host", default="127.0.0.1", help="server host")
    parser.add_argument("--port", type=int, default=7860, help="preferred server port")
    parser.add_argument("--no-browser", action="store_true", help="run only the local server without opening a window or browser")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    data_dir = resolve_data_dir(portable=args.portable)
    data_dir.mkdir(parents=True, exist_ok=True)

    db = Database(data_dir / "a2a_tester.sqlite3")
    db.connect()
    db.migrate()
    db.ensure_default_profile()

    try:
        app = create_app(db=db, data_dir=data_dir)
        if args.smoke_test:
            print("A2A Tester smoke OK")
            return 0

        run_desktop_app(app, args.host, args.port, no_browser=args.no_browser)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
