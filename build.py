"""One-command build for njuagent.

Steps: clean -> PyInstaller backend exe -> electron-builder portable app.
Run from the project root:  python build.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ELECTRON = os.path.join(ROOT, "electron")
ROOT_DIST = os.path.join(ROOT, "dist")
PYTHON = sys.executable


def log(step: str, msg: str) -> None:
    print(f"[build:{step}] {msg}", flush=True)


def run(cmd: list[str], cwd: str, step: str, env: dict | None = None) -> None:
    log(step, "running: " + " ".join(cmd))
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    proc = subprocess.run(cmd, cwd=cwd, env=full_env)
    if proc.returncode != 0:
        sys.exit(f"[build:{step}] FAILED (exit code {proc.returncode})")
    log(step, "ok")


def kill_njuagent_processes() -> None:
    """Best-effort kill of our own njuagent processes (app + backend) so the
    build output is never locked by a running instance. Dev-mode only; never
    touches other processes."""
    if os.name != "nt":
        return
    for name in ("njuagent.exe", "njuagent-backend.exe"):
        subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
        log("clean", f"taskkill {name} (best-effort)")


def clean() -> None:
    for p in [ROOT_DIST, os.path.join(ELECTRON, "dist"), os.path.join(ELECTRON, "release")]:
        if os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True)
            log("clean", f"removed {p}")


def main() -> None:
    log("start", "njuagent build")

    kill_njuagent_processes()
    clean()

    log("step", "1/2 packaging backend (PyInstaller)")
    run(
        [
            PYTHON,
            "-m", "PyInstaller",
            "--noconfirm", "--onefile",
            "--name", "njuagent-backend",
            "--paths", "src",
            "--collect-submodules", "uvicorn",
            "--add-data", "src/njuagent/server/static;njuagent/server/static",
            "build/entry.py",
        ],
        ROOT,
        "backend",
    )
    backend_exe = os.path.join(ROOT_DIST, "njuagent-backend.exe")
    if not os.path.isfile(backend_exe):
        sys.exit("[build:backend] exe not found at " + backend_exe)
    log("backend", f"ok: {backend_exe}")

    log("step", "2/2 packaging Electron (portable)")
    builder_cli = os.path.join(
        ELECTRON, "node_modules", "electron-builder", "out", "cli", "cli.js"
    )
    run(
        ["node", builder_cli, "--win", "portable", "--publish", "never"],
        ELECTRON,
        "electron",
        env={"ELECTRON_MIRROR": "https://npmmirror.com/mirrors/electron/"},
    )

    log("done", "artifacts:")
    log("done", "  " + os.path.join(ELECTRON, "dist", "win-unpacked"))
    for name in os.listdir(os.path.join(ELECTRON, "dist")):
        if name.endswith(".exe"):
            log("done", "  " + os.path.join(ELECTRON, "dist", name))


if __name__ == "__main__":
    main()
