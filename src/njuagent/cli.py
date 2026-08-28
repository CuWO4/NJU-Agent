"""CLI entry point for njuagent.

Starts an HTTP server for the given working directory, auto-detecting a free
port, and optionally opens the browser.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import threading
import webbrowser

import uvicorn

from .config import ConfigError, load_config
from .server.app import create_app

logger = logging.getLogger(__name__)


def find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="njuagent")
    parser.add_argument(
        "directory", nargs="?", default=".", help="working directory (default: current)"
    )
    parser.add_argument(
        "--port", type=int, default=0, help="HTTP port (default: auto-detect a free port)"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open the browser automatically"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc

    workdir = os.path.abspath(args.directory)
    port = args.port or find_free_port()
    url = f"http://127.0.0.1:{port}"

    app = create_app(workdir, config)
    logger.info("njuagent serving working directory: %s", workdir)
    logger.info("Web UI available at %s", url)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
