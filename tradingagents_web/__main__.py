"""`python -m tradingagents_web` — the only supported way to start the shell.

Three roles, one codebase:

* ``combined`` — pages and API in one process (the single-machine default);
* ``engine``   — the analysis API alone, normally bound to loopback;
* ``ui``       — the pages alone, forwarding ``/api`` to an engine.
"""

from __future__ import annotations

import argparse

import uvicorn

from .app import create_app

_ROLE_DEFAULTS = {"combined": ("0.0.0.0", 8501), "ui": ("0.0.0.0", 8501),
                  "engine": ("127.0.0.1", 8502)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tradingagents-web")
    parser.add_argument("--role", choices=sorted(_ROLE_DEFAULTS), default="combined",
                        help="combined (default), ui, or engine")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--db", default=None, help="SQLite path (default ~/.tradingagents/web/state.db)")
    parser.add_argument("--engine", default=None,
                        help="ui role: engine base URL (default http://127.0.0.1:8502)")
    parser.add_argument("--dev-no-token", action="store_true",
                        help="loopback development only: disable the shared token")
    args = parser.parse_args(argv)

    host, port = _ROLE_DEFAULTS[args.role]
    host = args.host or host
    port = args.port or port
    if args.dev_no_token and host not in ("127.0.0.1", "localhost"):
        parser.error("--dev-no-token is only allowed with --host 127.0.0.1")
    if args.role == "engine" and host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("the engine holds the queue and is bound to loopback; "
                     "expose it through the ui role instead")

    app = create_app(db_path=args.db, dev_no_token=args.dev_no_token,
                     role=args.role, engine_base=args.engine)
    uvicorn.run(app, host=host, port=port, workers=1, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
