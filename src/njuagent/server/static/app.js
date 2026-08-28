/* njuagent web UI logic (vanilla JS). */

const $ = (id) => document.getElementById(id);

const state = {
  taskId: null,
  currentPath: null,
  currentFilePending: false,
  autoApprove: false,
  planMode: false,
  thinkingEl: null,
  thinkingText: "",
  toolCards: {},
  uiManifest: {},
};

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

/* lightweight markdown renderer (safe: input is escaped first) */
function inlineMd(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

function renderMarkdown(src) {
  const escaped = escapeHtml(src);
  const blocks = [];
  let s = escaped.replace(/```([\s\S]*?)```/g, (_m, code) => {
    blocks.push(`<pre class="md-code">${code}</pre>`);
    return `\u0000${blocks.length - 1}\u0000`;
  });
  const lines = s.split("\n");
  const out = [];
  let inList = null;
  const flushList = () => {
    if (inList) {
      out.push(`</${inList}>`);
      inList = null;
    }
  };
  for (const line of lines) {
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushList();
      out.push(`<h${h[1].length}>${inlineMd(h[2])}</h${h[1].length}>`);
      continue;
    }
    if (/^\s*$/.test(line)) {
      flushList();
      continue;
    }
    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ul || ol) {
      const kind = ul ? "ul" : "ol";
      if (inList !== kind) {
        flushList();
        inList = kind;
        out.push(`<${kind}>`);
      }
      out.push(`<li>${inlineMd(ul ? ul[1] : ol[1])}</li>`);
      continue;
    }
    flushList();
    out.push(`<p>${inlineMd(line)}</p>`);
  }
  flushList();
  let html = out.join("\n");
  html = html.replace(/\u0000(\d+)\u0000/g, (_m, i) => blocks[Number(i)]);
  return html;
}

async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail || detail;
    } catch (_e) { /* keep statusText */ }
    throw new Error(detail);
  }
  return resp.json();
}

const postJson = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

const PLAN_PREFIX =
  "<system reminder>plan mode is opened in this turn of conversation</system reminder>";

function stripPlanPrefix(text) {
  if (text.startsWith(PLAN_PREFIX)) {
    return text.slice(PLAN_PREFIX.length).replace(/^\n+/, "");
  }
  return text;
}

/* ---------- conversation rendering ---------- */

function addUserMessage(text, index) {
  const div = document.createElement("div");
  div.className = "user";
  div.innerHTML = renderMarkdown(stripPlanPrefix(text));
  if (index !== undefined) {
    div.dataset.index = index;
    div.dataset.raw = text;
    const btn = document.createElement("button");
    btn.className = "edit-btn";
    btn.textContent = "Edit";
    btn.title = "Edit this message and rewind the conversation from here";
    btn.onclick = () => startEdit(div);
    div.appendChild(btn);
  }
  $("messages").appendChild(div);
  div.scrollIntoView({ block: "end" });
}

function startEdit(div) {
  const raw = div.dataset.raw || "";
  div.classList.add("editing");
  div.innerHTML = "";
  const ta = document.createElement("textarea");
  ta.className = "edit-input";
  ta.value = raw;
  const save = document.createElement("button");
  save.className = "edit-save";
  save.textContent = "Save";
  const cancel = document.createElement("button");
  cancel.className = "edit-cancel";
  cancel.textContent = "Cancel";
  save.onclick = async () => {
    try {
      await postJson("/api/messages/edit", {
        index: Number(div.dataset.index),
        content: ta.value,
      });
      await reloadConversation();
    } catch (err) {
      showError(err.message);
    }
  };
  cancel.onclick = reloadConversation;
  div.append(ta, save, cancel);
  ta.focus();
}

async function reloadConversation() {
  try {
    const s = await api("/api/state");
    state.uiManifest = {};
    for (const t of s.ui_manifest || []) state.uiManifest[t.name] = t;
    renderHistory(s.messages);
    await renderPending();
  } catch (err) {
    showError(err.message);
  }
}

function appendThinking(text) {
  if (!state.thinkingEl) {
    state.thinkingEl = document.createElement("div");
    state.thinkingEl.className = "thinking";
    $("messages").appendChild(state.thinkingEl);
  }
  state.thinkingText += text;
  state.thinkingEl.innerHTML = renderMarkdown(state.thinkingText);
  state.thinkingEl.scrollIntoView({ block: "end" });
}

function endThinking(content) {
  if (state.thinkingEl) {
    state.thinkingEl.classList.add("final");
    state.thinkingEl = null;
    state.thinkingText = "";
  } else if (content) {
    const div = document.createElement("div");
    div.className = "assistant final";
    div.innerHTML = renderMarkdown(content);
    $("messages").appendChild(div);
    div.scrollIntoView({ block: "end" });
  }
}

function collapseThinking() {
  if (!state.thinkingEl) return;
  const html = state.thinkingEl.innerHTML;
  if (html) {
    const det = document.createElement("details");
    det.className = "thinking";
    const sum = document.createElement("summary");
    sum.textContent = "Thinking";
    det.appendChild(sum);
    const body = document.createElement("div");
    body.className = "assistant";
    body.innerHTML = html;
    det.appendChild(body);
    state.thinkingEl.replaceWith(det);
  } else {
    state.thinkingEl.remove();
  }
  state.thinkingEl = null;
  state.thinkingText = "";
}

function makeToolCard(ev, withResult) {
  const card = document.createElement("div");
  card.className = "tool-card";
  card.dataset.id = ev.id;
  const status = withResult ? "done" : ev.status === "waiting_approval" ? "awaiting approval" : "running";
  const argsText = Array.isArray(ev.ui_args) ? ev.ui_args.join("\n") : "";
  card.innerHTML =
    `<div class="tool-head"><span class="tool-name">${escapeHtml(ev.ui_name || ev.name)}</span>` +
    `<span class="tool-status">${status}</span></div>` +
    (argsText ? `<div class="tool-args-inline"><pre>${escapeHtml(argsText)}</pre></div>` : "") +
    `<div class="approval-row" hidden>` +
    `<button class="allow">Allow</button><button class="skip">Skip</button>` +
    `<button class="adjust">Adjust approval mode</button></div>`;
  $("messages").appendChild(card);
  state.toolCards[ev.id] = card;
  card.scrollIntoView({ block: "end" });
  return card;
}

function renderToolCall(ev) {
  collapseThinking();
  makeToolCard(ev, false);
}

function renderToolCallFromHistory(tc) {
  const info = state.uiManifest[tc.function.name] || {
    ui_name: tc.function.name,
    ui_args: null,
  };
  let values = [];
  try {
    const args = JSON.parse(tc.function.arguments || "{}");
    const keys = info.ui_args || Object.keys(args);
    values = keys
      .filter((k) => k in args)
      .map((k) => (typeof args[k] === "string" ? args[k] : JSON.stringify(args[k])));
  } catch (_e) {
    values = [tc.function.arguments];
  }
  makeToolCard(
    {
      id: tc.id,
      name: tc.function.name,
      ui_name: info.ui_name,
      ui_args: values,
      status: "running",
    },
    false
  );
  state.toolCards[tc.id].querySelector(".tool-status").textContent = "done";
}

function showApproval(ev) {
  const card = state.toolCards[ev.id];
  if (!card) return;
  const row = card.querySelector(".approval-row");
  row.hidden = false;
  card.querySelector(".tool-status").textContent = "awaiting approval";
  row.querySelector(".allow").onclick = () =>
    postJson("/api/approval", { approved: true }).catch(console.error);
  row.querySelector(".skip").onclick = () =>
    postJson("/api/approval", { approved: false }).catch(console.error);
  row.querySelector(".adjust").onclick = async () => {
    state.autoApprove = true;
    $("autoApprove").checked = true;
    await postJson("/api/settings", { auto_approve: true }).catch(console.error);
  };
}

function resolveApproval(ev) {
  const card = state.toolCards[ev.id];
  if (!card) return;
  card.querySelector(".approval-row").hidden = true;
  card.querySelector(".tool-status").textContent = ev.approved ? "approved" : "denied";
}

function showToolResult(ev) {
  // tool results are intentionally not shown in the conversation; only the
  // fact that the tool was called is visible
  const card = state.toolCards[ev.id];
  if (!card) return;
  card.querySelector(".tool-status").textContent = "done";
}

function showError(message) {
  const div = document.createElement("div");
  div.className = "assistant";
  div.textContent = "Error: " + message;
  $("messages").appendChild(div);
  div.scrollIntoView({ block: "end" });
}

/* ---------- cost ---------- */

let totalPrompt = 0;
let totalCompletion = 0;

function updateCost(usage) {
  totalPrompt += usage.prompt_tokens || 0;
  totalCompletion += usage.completion_tokens || 0;
  $("cost").textContent = `in ${totalPrompt} / out ${totalCompletion} tok`;
}

/* ---------- SSE ---------- */

function connect(taskId) {
  const es = new EventSource(`/api/stream/${taskId}`);
  es.onmessage = (e) => {
    let ev;
    try {
      ev = JSON.parse(e.data);
    } catch (_err) {
      return;
    }
    handleEvent(ev);
  };
  es.onerror = () => {
    // The stream ended (task finished) or the server restarted; close the
    // connection so the browser does not keep reconnecting to a dead task.
    es.close();
  };
  return es;
}

function handleEvent(ev) {
  switch (ev.type) {
    case "message.delta": appendThinking(ev.content); break;
    case "message.done": endThinking(ev.content); break;
    case "tool.call": renderToolCall(ev); break;
    case "approval.request": showApproval(ev); break;
    case "approval.resolved": resolveApproval(ev); break;
    case "tool.result": showToolResult(ev); break;
    case "pending.changed": renderPending(); break;
    case "cost": updateCost(ev.usage); break;
    case "error": showError(ev.message); break;
    case "ended": endTask(); break;
    default: break;
  }
}

/* ---------- task control ---------- */

function setRunning(running) {
  const btn = $("sendBtn");
  btn.textContent = running ? "Stop" : "Send";
  btn.classList.toggle("stop", running);
  btn.disabled = false;
}

async function sendMessage() {
  const text = $("input").value.trim();
  if (!text || state.taskId) return;
  $("input").value = "";
  addUserMessage(text);
  setRunning(true);
  try {
    const resp = await postJson("/api/chat", { message: text });
    state.taskId = resp.task_id;
    connect(resp.task_id);
  } catch (err) {
    showError(err.message);
    setRunning(false);
  }
}

function stopTask() {
  if (state.taskId) postJson("/api/stop", { task_id: state.taskId }).catch(console.error);
}

function endTask() {
  state.taskId = null;
  setRunning(false);
  $("input").focus();
}

/* ---------- directory tree ---------- */

function joinPath(base, name) {
  return base === "." || base === "" ? name : `${base}/${name}`;
}

async function openFile(path) {
  try {
    const f = await api(`/api/file?path=${encodeURIComponent(path)}`);
    state.currentPath = path;
    state.currentFilePending = f.pending;
    const editor = $("editor");
    editor.value = f.content;
    editor.disabled = false;
    $("editorTitle").textContent = path;
    $("saveBtn").disabled = f.pending;
    $("fileStatus").textContent = f.pending
      ? "has pending changes - accept or rollback first"
      : "";
    markTreeSelection(path);
  } catch (err) {
    $("fileStatus").textContent = err.message;
  }
}

function markTreeSelection(path) {
  document.querySelectorAll(".tree .node.selected").forEach((n) => n.classList.remove("selected"));
  const node = document.querySelector(`.tree .node[data-path="${CSS.escape(path)}"]`);
  if (node) node.classList.add("selected");
}

function makeNode(relPath, entries) {
  const ul = document.createElement("ul");
  for (const e of entries) {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.className = "node " + e.type;
    label.dataset.path = joinPath(relPath, e.name);
    label.textContent = e.name;
    const full = joinPath(relPath, e.name);
    if (e.type === "dir") {
      const childUl = document.createElement("ul");
      childUl.hidden = true;
      label.onclick = async () => {
        if (childUl.hidden) {
          childUl.hidden = false;
          if (!childUl.dataset.loaded) {
            try {
              const sub = await api(`/api/list?path=${encodeURIComponent(full)}`);
              childUl.appendChild(makeNode(full, sub.entries));
              childUl.dataset.loaded = "1";
            } catch (err) {
              label.textContent = e.name + " (error)";
            }
          }
        } else {
          childUl.hidden = true;
        }
      };
      li.appendChild(label);
      li.appendChild(childUl);
    } else {
      label.onclick = () => openFile(full);
      li.appendChild(label);
    }
    ul.appendChild(li);
  }
  return ul;
}

async function renderTree() {
  const tree = $("tree");
  tree.innerHTML = "";
  try {
    const root = await api("/api/list?path=.");
    tree.appendChild(makeNode(".", root.entries));
  } catch (err) {
    tree.textContent = "Error loading tree: " + err.message;
  }
}

/* ---------- pending panel ---------- */

async function renderPending() {
  const box = $("pendingBox");
  const list = $("pendingList");
  let files = [];
  try {
    files = (await api("/api/pending")).files;
  } catch (_err) {
    return;
  }
  list.innerHTML = "";
  if (files.length === 0) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  for (const f of files) {
    const row = document.createElement("div");
    row.className = "pending-row";
    const info = document.createElement("details");
    const sum = document.createElement("summary");
    sum.textContent = f.path;
    const pre = document.createElement("pre");
    pre.textContent = f.diff || "(new file)";
    info.appendChild(sum);
    info.appendChild(pre);
    const ok = document.createElement("button");
    ok.className = "p-accept";
    ok.textContent = "OK";
    ok.title = "Accept changes";
    const x = document.createElement("button");
    x.className = "p-rollback";
    x.textContent = "X";
    x.title = "Rollback to last confirmed state";
    ok.onclick = async () => {
      await postJson("/api/pending/accept", { path: f.path }).catch(console.error);
      await refreshAfterPending(f.path);
    };
    x.onclick = async () => {
      await postJson("/api/pending/rollback", { path: f.path }).catch(console.error);
      await refreshAfterPending(f.path);
    };
    row.appendChild(info);
    row.appendChild(ok);
    row.appendChild(x);
    list.appendChild(row);
  }
}

async function refreshAfterPending(path) {
  await renderPending();
  if (state.currentPath === path) await openFile(path);
}

/* ---------- init ---------- */

async function init() {
  $("inputForm").addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.taskId) stopTask();
    else sendMessage();
  });
  $("autoApprove").addEventListener("change", async (e) => {
    state.autoApprove = e.target.checked;
    await postJson("/api/settings", { auto_approve: state.autoApprove }).catch(console.error);
  });
  $("planMode").addEventListener("change", async (e) => {
    state.planMode = e.target.checked;
    await postJson("/api/settings", { plan_mode: state.planMode }).catch(console.error);
  });
  $("saveBtn").addEventListener("click", async () => {
    try {
      await postJson("/api/file", { path: state.currentPath, content: $("editor").value });
      $("fileStatus").textContent = "saved";
    } catch (err) {
      $("fileStatus").textContent = err.message;
    }
  });
  $("acceptAll").addEventListener("click", async () => {
    await postJson("/api/pending/accept", { all: true }).catch(console.error);
    await refreshAfterPending(null);
  });
  $("rollbackAll").addEventListener("click", async () => {
    await postJson("/api/pending/rollback", { all: true }).catch(console.error);
    await refreshAfterPending(null);
  });
  $("editor").addEventListener("keydown", (e) => {
    if (e.key === "s" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      $("saveBtn").click();
    }
  });

  try {
    const s = await api("/api/state");
    $("workdir").textContent = s.workdir;
    $("workdir").title = s.workdir;
    $("planMode").checked = s.plan_mode;
    $("autoApprove").checked = s.auto_approve;
    state.autoApprove = s.auto_approve;
    state.planMode = s.plan_mode;
    state.uiManifest = {};
    for (const t of s.ui_manifest || []) state.uiManifest[t.name] = t;
    renderHistory(s.messages);
    await renderPending();
    await renderTree();
  } catch (err) {
    $("messages").textContent = "Failed to load state: " + err.message;
  }
}

function renderHistory(messages) {
  const box = $("messages");
  box.innerHTML = "";
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.role === "system") continue;
    if (m.role === "user") {
      addUserMessage(m.content, i);
    } else if (m.role === "assistant") {
      if (m.content) {
        const div = document.createElement("div");
        div.className = "assistant";
        div.innerHTML = renderMarkdown(m.content);
        box.appendChild(div);
      }
      for (const tc of m.tool_calls || []) {
        renderToolCallFromHistory(tc);
      }
    }
  }
  box.scrollTop = box.scrollHeight;
}

window.addEventListener("DOMContentLoaded", init);
