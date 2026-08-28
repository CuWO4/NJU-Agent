# njuagent - Design Specification (Draft)

> Status: Draft for phase 2 (planning). Will evolve during implementation.

## 1. Overview

`njuagent` is a self-built coding agent (programming agent), not a chatbot. It
drives a DeepSeek model through a tool-calling loop to autonomously read/write
files and execute commands in a working directory, similar to a simplified
Claude Code / Codex.

- Language: Python
- Model: DeepSeek (OpenAI-compatible API, native function calling)
- UI: Web page (classic IDE layout), served by an embedded HTTP server
- Entry: CLI launcher that prints logs and starts the HTTP server

### Boundaries (task requirements)

- All important logic is self-implemented: conversation history & context
  management, tool definition & local execution, model output parsing, loop
  termination, error handling.
- Not allowed: wrapping an existing agent product; agent frameworks/SDKs
  (LangChain, LlamaIndex, OpenAI Agents SDK, Claude Agent SDK, AutoGen,
  CrewAI, ...); server-hosted code execution / file tools (Code Interpreter,
  Files API).
- Allowed: model vendor API client libraries, OpenAI-compatible gateways,
  native tool-calling interface.

## 2. Architecture

Single process. The CLI starts an HTTP server and the agent core in the same
process; there is no separate backend/frontend deployment.

```
cli (njuagent) --launch--> FastAPI/uvicorn server
                                |-- serves static web UI  (/)
                                |-- REST + SSE endpoints   (/api/*)
                                |-- agent core (in-process)
                                       |-- session state
                                       |-- agent loop
                                       |-- tool executor
                                       |-- persistence (.njuagent/)
```

- Web UI: single-page native HTML/JS/CSS, no build step, served statically by
  FastAPI. Server-Sent Events (SSE) push streaming updates (assistant text,
  tool calls, tool results, pending-change events, cost info).
- Model transport: direct REST calls to the DeepSeek OpenAI-compatible chat
  completions endpoint via `httpx` (streaming). No vendor SDK; request
  construction, SSE-format response parsing, tool-call handling and retries
  are self-implemented.
- Frontend layout (IDE-like):
  - Left: directory tree of the working directory
  - Center: file viewer/editor (readable and writable; no syntax highlighting,
    no diff editor)
  - Right: conversation with the model (waterfall; thinking steps collapsible)
  - A separate panel lists pending file changes (see section 5)
- Working directory: the directory the CLI is launched in. One session maps to
  exactly one working directory. A CLI instance serves exactly one directory;
  switching directory means restarting the CLI. The HTTP server binds to an
  auto-detected free port, so multiple instances do not conflict.

SSE event protocol (preliminary, one JSON event per `data:` line):

- `message.delta` - assistant text chunk
- `message.done` - assistant message complete
- `tool.call` - a tool call started (name, arguments, id)
- `tool.result` - tool result ready
- `tool.approval` - approval requested (tool execution blocked)
- `pending.changed` - pending-change set changed
- `session.state` - full state snapshot (reload/restore)
- `cost` - token usage / estimated cost update
- `error` - error event
- `ended` - agent loop ended (natural or user-aborted)

## 3. Core agent loop

State per session: list of messages (system prompt, user messages, assistant
messages, tool calls, tool results) + pending-change set + model config.

Loop:

1. Assemble messages (system prompt + history + latest user message).
2. Call the DeepSeek chat completions REST API directly via `httpx`
   (streaming, OpenAI-compatible format). Track token usage from API `usage`.
3. Parse response (SSE-format stream assembled into a ChatCompletion object;
   parsing is self-implemented):
   - No `tool_calls` in response -> the model is done; end the loop, surface
     final assistant text.
   - Has `tool_calls` -> execute each tool (see section 4), possibly blocking
     on user approval.
4. Append tool results as tool messages.
5. Repeat from 2. A user "stop" button aborts the loop between iterations;
   there is no forced interruption from the tool side.

Termination: model stops requesting tools (natural end) or user aborts.

Error handling:

- API errors (network, rate limit): automatic retry with exponential backoff.
- Tool execution failure: the error text is returned to the model as the tool
  result so the model can self-correct.

### System prompt outline (hardcoded)

- Identity: a coding agent operating inside a given working directory.
- Tool usage: read before modifying; use `search` for exploration; prefer
  small, incremental edits.
- Working-directory discipline: prefer operations inside the working
  directory; out-of-directory operations require approval and may be denied.
- Command usage: consider timeouts for long-running commands.
- Termination: when the task is complete, stop and give a concise final
  summary (no tool calls).
- Plan mode: when the plan-mode prefix is present, first produce a plan
  without modifying files, then await approval to execute.
- Sub-agent rules (main agent): do not delegate command execution or
  out-of-directory I/O to sub-agents (they may fail); sub-agents are for
  isolated sub-tasks.
- Sub-agent rules (sub-agent): approval-requiring tools are denied by
  default; work only through non-approved tools.

## 4. Tools

Self-defined via JSON schema (function-calling format). Initial toolset:

| Tool         | Purpose                                      |
|--------------|----------------------------------------------|
| `list_dir`   | List entries of a directory                  |
| `read_file`  | Read a file (with line range support)        |
| `write_file` | Write a file (immediately persisted)         |
| `run_command`| Run a shell command in the working directory |
| `search`     | Recursive glob + content search (Python impl)|

Execution notes:

- `run_command`: detect host OS and use the corresponding shell (Windows:
  cmd/PowerShell; POSIX: sh/bash). Run inside the working directory. Optional
  timeout (kill process tree). Requires explicit user approval unless the
  session has auto-approve mode on (see section 6).
- `write_file`: write immediately to disk; record a snapshot of the previous
  file content into the session's pending-change set (see section 5). The
  model is not aware of approval/rollback.
- `search`: pure Python (no system grep dependency), glob + regex content
  match.

## 5. Pending file changes (accept / rollback)

- The model's write goes to disk immediately and is visible to the model and
  all other processes.
- Each write records a snapshot (previous content) into a pending-change set
  keyed by file path. The pending set is bounded by the last "confirmed"
  baseline.
- UI panel "Modified files": lists files with pending changes. Each entry shows
  a lightweight per-line diff and has accept / rollback actions. A shortcut
  "accept all" / "rollback all" is available.
- Rollback restores the file to the last confirmed state. This is
  file-system-level and invisible to the model.
- Manual edits by the user never enter the pending set. To keep diff
  integrity, a file with pending (unconfirmed) changes cannot be manually
  edited in the center editor; the user must accept or rollback it first.
- Before a conversation rollback/edit, unresolved pending changes must be
  resolved (accept or rollback); an indeterminate state is not allowed.

## 6. Approval & security

- Commands require explicit approval unless auto-approve is on.
- Approval is rendered inline in the conversation waterfall: a tool-call card
  with [Allow] [Skip] [Adjust approval mode]. Approving blocks tool execution
  until the user acts.
- Auto-approve mode is a per-session toggle.
- File tools are restricted to the working directory. Reads/writes inside
  the working directory need no approval; reads/writes outside require
  per-operation approval (each operation is judged independently; approval of
  one out-of-dir operation does not authorize later ones). After approval the
  operation proceeds like a normal one.
- File writes inside the working directory do not require approval.
- API key comes from environment variables only (never committed).

## 7. Session model & persistence

- One session per working directory. Sessions live under `./.njuagent/`.
- Persisted data: conversation messages, pending-change snapshots, plan/todo
  state, session metadata.
- Session restore: fully restore and continue (history + file snapshot state).
- A session can host multiple parallel sub-agents (multiagent, see section 8).

Storage layout (under the working directory):

```
.njuagent/
  sessions/<session-id>/
    meta.json        # working dir, model, settings (auto-approve, plan mode)
    messages.jsonl   # conversation history
    pending/         # snapshots for pending changes
    plan.md          # plan/todo state
  skills/*.md        # preset skill prompts (text only)
```

## 8. Features

1. Plan mode - system prompt declares a special user prefix (e.g. `<system
   reminder>plan mode is opened in this turn of conversation</system
   reminder>`). When UI plan mode is on, the prefix is prepended to the user
   request; the frontend does not render this prefix.
2. Conversation compression - when context length approaches the limit,
   automatically call the API to compress older history. Simple strategy is
   acceptable (unlikely to be exercised in demos).
3. Dynamic skills - preset files under `.njuagent/skills/*.md` containing only
   prompt text (no tools). Skill text is inserted/removed from the system
   prompt.
4. Multiagent - spawn parallel sub-agents, each with a special system prompt;
   sub-agents run in the same session. Sub-agents are invisible to the user.
   Unless the session is in auto-approve mode, actions requiring approval are
   rejected for sub-agents. Their system prompt states that approval-requiring
   tools are denied by default; the main agent's system prompt warns not to
   delegate command execution or out-of-directory I/O to sub-agents (they may
   fail).
5. Conversation management - edit the content of a past message and resend;
   this pulls the conversation state back to that point (no file side
   effects). Unresolved pending changes must be resolved first. Undoing tool
   results is out of scope.
6. Thinking-step collapse - assistant reasoning is collapsible in the UI
   (basic frontend behavior).
7. Command timeout - enforce timeout and kill the process tree; also the
   system prompt asks the model to consider timeouts for long commands.
8. Cost/token display - show token usage / estimated cost if the API provides
   it.

## 9. Dependencies & configuration

CLI interface:

```
njuagent [DIRECTORY] [--port PORT] [--no-browser]
```

- `DIRECTORY` defaults to the current directory; it becomes the working
  directory and the session is bound to it.
- `--port` binds a specific port; by default an idle free port is detected
  automatically.
- `--no-browser` skips auto-opening the browser.

Third-party dependencies (minimal set; no agent frameworks, no vendor SDK):

- `fastapi` + `uvicorn` - embedded HTTP server (static UI, REST, SSE)
- `httpx` - async streaming HTTP client for DeepSeek REST API
- `pytest` - unit tests

Deliberately not used: `openai` SDK (too heavy for our needs; direct REST
keeps full control) and `psutil` (process-tree kill via platform commands:
Windows `taskkill /F /T /PID`, POSIX `os.killpg`).

Environment variable: `DEEPSEEK_API_KEY` (or `NJUAGENT_API_KEY`).

- Model: fixed DeepSeek (chat model, base_url for OpenAI-compatible endpoint).
- Per-session settings: auto-approve toggle, plan mode.

## 10. Project structure (target)

```
njuagent/
  pyproject.toml
  README.md
  src/njuagent/
    __init__.py
    cli.py              # entry: parse args, start server, logs
    config.py           # env/config loading
    server/
      app.py            # FastAPI app, routes, SSE
      static/           # index.html, app.js, style.css
    agent/
      client.py         # httpx-based DeepSeek REST client (streaming)
      session.py        # session state, persistence
      loop.py           # agent loop, termination, retry
      context.py        # message assembly, token counting
      parser.py         # SSE-format stream + tool-calling response parsing
      prompts.py        # system prompts (hardcoded)
      skills.py         # dynamic skill loading
    tools/
      registry.py       # tool schema definition
      fs.py             # list_dir / read_file / write_file
      command.py        # run_command with approval & timeout
      search.py         # glob + content search
    store/
      snapshots.py      # pending-change snapshots, accept/rollback
    approval.py         # approval state, auto-approve
  tests/
    test_parser.py
    test_tools.py
    test_context.py
    test_snapshots.py
    test_session.py
  docs/DESIGN.md
```

## 11. Testing strategy

- Unit tests (pytest) for core mechanisms: response parsing, tool schemas &
  execution, context assembly, snapshot accept/rollback, session persistence.
- Manual end-to-end verification with real tasks.

## 12. Roadmap (small steps)

- M1: Minimal loop - CLI starts server; single session; read/write/list/run
  tools; auto-approve on; model natural end.
- M2: Web UI three-pane layout + SSE streaming + tool cards + inline approval.
- M3: Pending-change panel (snapshots/rollback), session persistence/restore.
- M4: Features - plan mode, skills, multiagent, compression, conversation
  management.
- M5: Polish, unit tests completion, README, demo task, video.
