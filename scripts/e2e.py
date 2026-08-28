"""M1 end-to-end smoke test against the real DeepSeek API.

Runs the agent loop in a temporary working directory with a small real task.
Requires DEEPSEEK_API_KEY to be available (environment or .env in the CWD).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

from njuagent.agent.client import DeepSeekClient
from njuagent.agent.loop import AgentLoop
from njuagent.agent.prompts import build_main_prompt
from njuagent.agent.session import Session
from njuagent.approval import ApprovalGate
from njuagent.config import load_config
from njuagent.store.snapshots import PendingChanges
from njuagent.tools import build_tool_registry

TASK = (
    "Create a Python file hello.py that prints 'Hello from njuagent', then "
    "run it with python and report the output."
)


async def main() -> None:
    config = load_config()
    ws = tempfile.mkdtemp(prefix="njuagent-e2e-")
    print("workdir:", ws)
    pending = PendingChanges()
    session = Session(ws, build_main_prompt())
    client = DeepSeekClient(config.api_key, config.base_url, config.model)
    loop = AgentLoop(
        session,
        client,
        build_tool_registry(ws, pending),
        ApprovalGate(),
        pending,
    )
    print(">>> task:", TASK)
    result = await loop.run(TASK)
    print("=== final ===")
    print(result)
    print("=== iterations:", loop.iterations)
    print("=== files created ===")
    for root, _dirs, files in os.walk(ws):
        for name in files:
            print(os.path.join(root, name))
    hp = os.path.join(ws, "hello.py")
    if os.path.isfile(hp):
        print("=== hello.py ===")
        print(open(hp, encoding="utf-8").read())
    shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
