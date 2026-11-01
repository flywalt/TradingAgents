"""`python -m tradingagents_web` — the only supported way to start the shell."""

from __future__ import annotations

import argparse

import uvicorn

from .app import create_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tradingagents-web")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--db", default=None, help="SQLite path (default ~/.tradingagents/web/state.db)")
    parser.add_argument("--dev-no-token", action="store_true",
                        help="loopback development only: disable the shared token")
    args = parser.parse_args(argv)
    if args.dev_no_token and args.host not in ("127.0.0.1", "localhost"):
        parser.error("--dev-no-token is only allowed with --host 127.0.0.1")
    app = create_app(db_path=args.db, dev_no_token=args.dev_no_token)
    uvicorn.run(app, host=args.host, port=args.port, workers=1, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
