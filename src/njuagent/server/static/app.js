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
  searchOpts: { case: false, word: false, regex: false },
  selectedPath: null,
  selectedIsDir: false,
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
  let s = escaped.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
    const cls = lang ? ` language-${lang}` : "";
    blocks.push(`<pre class="md-code"><code class="${cls}">${code}</code></pre>`);
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

/* syntax highlight code blocks inside a rendered element */
function highlightBlocks(root) {
  if (typeof hljs === "undefined" || !root) return;
  root.querySelectorAll("pre.md-code code").forEach((el) => hljs.highlightElement(el));
}

/* pick a CodeMirror mode from a file path */
function modeForPath(path) {
  const ext = path.split(".").pop().toLowerCase();
  const map = {
    py: "python", js: "javascript", mjs: "javascript", ts: "javascript",
    html: "htmlmixed", htm: "htmlmixed", vue: "htmlmixed",
    css: "css", scss: "css", less: "css",
    json: "javascript", md: "markdown", markdown: "markdown",
    xml: "xml", svg: "xml",
    java: "text/x-java", c: "text/x-csrc", h: "text/x-csrc",
    cpp: "text/x-c++src", cc: "text/x-c++src", cxx: "text/x-c++src",
  };
  return map[ext] || "text/plain";
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
  highlightBlocks(div);
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
    highlightBlocks(state.thinkingEl);
    state.thinkingEl = null;
    state.thinkingText = "";
  } else if (content) {
    const div = document.createElement("div");
    div.className = "assistant final";
    div.innerHTML = renderMarkdown(content);
    highlightBlocks(div);
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
    highlightBlocks(body);
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
    case "shell.changed": renderShell(); break;
    case "pending.changed":
      renderPending();
      renderTree();
      refreshCurrentFile();
      break;
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

/* ---------- editor ---------- */

let editorCM = null;

function initEditor() {
  const ta = $("editor");
  editorCM = CodeMirror.fromTextArea(ta, {
    lineNumbers: true,
    theme: "vs-dark",
    mode: "text/plain",
    readOnly: true,
    extraKeys: {
      "Ctrl-S": () => $("saveBtn").click(),
      "Cmd-S": () => $("saveBtn").click(),
    },
  });
}

async function openFile(path) {
  try {
    const f = await api(`/api/file?path=${encodeURIComponent(path)}`);
    state.currentPath = path;
    state.currentFilePending = f.pending;
    editorCM.setValue(f.content);
    editorCM.setOption("mode", modeForPath(path));
    editorCM.setOption("readOnly", f.pending);
    editorCM.refresh();
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

const FILE_ICONS = {
  py: "file_type_python", js: "file_type_js", mjs: "file_type_js", ts: "file_type_typescript",
  html: "file_type_html", htm: "file_type_html", css: "file_type_css", scss: "file_type_css",
  json: "file_type_json", md: "file_type_markdown", markdown: "file_type_markdown",
  yaml: "file_type_yaml", yml: "file_type_yaml", xml: "file_type_xml", toml: "file_type_toml",
  c: "file_type_c", h: "file_type_c", cpp: "file_type_cpp", cc: "file_type_cpp",
  java: "file_type_java", rs: "file_type_rust", go: "file_type_go",
  txt: "file_type_text", text: "file_type_text", log: "file_type_text",
  png: "file_type_image", jpg: "file_type_image", jpeg: "file_type_image",
  gif: "file_type_image", svg: "file_type_image", webp: "file_type_image", ico: "file_type_image",
  zip: "file_type_zip", gz: "file_type_zip", tar: "file_type_zip", "7z": "file_type_zip", rar: "file_type_zip",
  pdf: "file_type_pdf",
  ini: "file_type_config", cfg: "file_type_config", conf: "file_type_config",
  license: "file_type_license", editorconfig: "file_type_editorconfig",
};

function iconForPath(name) {
  const ext = name.split(".").pop().toLowerCase();
  return FILE_ICONS[ext] || "default_file";
}

function makeNode(relPath, entries) {
  const ul = document.createElement("ul");
  for (const e of entries) {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.className = "node " + e.type;
    label.dataset.path = joinPath(relPath, e.name);
    const icon = document.createElement("img");
    icon.className = "file-icon";
    icon.alt = "";
    const full = joinPath(relPath, e.name);
    const selectNode = () => {
      state.selectedPath = full;
      state.selectedIsDir = e.type === "dir";
      markTreeSelection(full);
    };
    if (e.type === "dir") {
      icon.src = "/static/vendor/icons/default_folder.svg";
      label.appendChild(icon);
      label.appendChild(document.createTextNode(e.name));
      label.draggable = true;
      label.addEventListener("dragstart", (ev) => {
        ev.dataTransfer.setData("text/plain", full);
      });
      label.addEventListener("dragover", (ev) => ev.preventDefault());
      label.addEventListener("drop", async (ev) => {
        ev.preventDefault();
        const src = ev.dataTransfer.getData("text/plain");
        if (src && src !== full && !src.startsWith(full + "/")) {
          await postJson("/api/file/move", { path: src, dest_dir: full }).catch(console.error);
          await renderTree();
        }
      });
      const childUl = document.createElement("ul");
      childUl.hidden = true;
      label.onclick = async () => {
        selectNode();
        if (childUl.hidden) {
          childUl.hidden = false;
          label.classList.add("expanded");
          icon.src = "/static/vendor/icons/default_folder_opened.svg";
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
          label.classList.remove("expanded");
          icon.src = "/static/vendor/icons/default_folder.svg";
        }
      };
      li.appendChild(label);
      li.appendChild(childUl);
    } else {
      icon.src = "/static/vendor/icons/" + iconForPath(e.name) + ".svg";
      label.appendChild(icon);
      label.appendChild(document.createTextNode(e.name));
      label.draggable = true;
      label.addEventListener("dragstart", (ev) => {
        ev.dataTransfer.setData("text/plain", full);
      });
      label.onclick = () => {
        selectNode();
        openFile(full);
      };
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

function dirOfSelected() {
  if (!state.selectedPath) return "";
  if (state.selectedIsDir) return state.selectedPath;
  const parts = state.selectedPath.split("/");
  parts.pop();
  return parts.join("/");
}

function showInlineInput(defaultValue, placeholder, onSubmit) {
  let input = document.querySelector("#treeInlineInput");
  if (!input) {
    input = document.createElement("input");
    input.id = "treeInlineInput";
    input.className = "tree-inline-input";
    document.querySelector("#tree").appendChild(input);
  }
  input.value = defaultValue;
  input.placeholder = placeholder || "";
  input.style.display = "block";
  input.focus();
  input.select();
  const finish = (ok) => {
    const val = input.value.trim();
    input.style.display = "none";
    input.removeEventListener("keydown", handler);
    if (ok && val) onSubmit(val);
  };
  const handler = (e) => {
    if (e.key === "Enter") finish(true);
    else if (e.key === "Escape") finish(false);
  };
  input.addEventListener("keydown", handler);
}

function initTreeOps() {
  $("tree").addEventListener("dblclick", async (e) => {
    if (e.target.closest(".node")) return;
    showInlineInput("", "name (end with / for a folder)", async (name) => {
      const isDir = name.endsWith("/");
      const clean = isDir ? name.slice(0, -1) : name;
      if (!clean) return;
      const dir = dirOfSelected();
      const path = dir ? dir + "/" + clean : clean;
      await postJson("/api/file/create", { path, is_dir: isDir }).catch(console.error);
      await renderTree();
    });
  });
  window.addEventListener("keydown", async (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "z") {
      if (e.target.closest(".CodeMirror, input, textarea")) return;
      e.preventDefault();
      await postJson("/api/file/undo", {}).catch(console.error);
      await renderTree();
      return;
    }
    if (!state.selectedPath) return;
    if (e.target.closest(".CodeMirror, input, textarea")) return;
    if (e.key === "Delete") {
      e.preventDefault();
      await fetch(`/api/file?path=${encodeURIComponent(state.selectedPath)}`, { method: "DELETE" })
        .catch(console.error);
      await renderTree();
    } else if (e.key === "F2") {
      e.preventDefault();
      const oldName = state.selectedPath.split("/").pop();
      showInlineInput(oldName, "", async (newName) => {
        if (newName !== oldName) {
          await postJson("/api/file/rename", { path: state.selectedPath, new_name: newName })
            .catch(console.error);
          await renderTree();
        }
      });
    }
  });
}

/* ---------- shared shell ---------- */

function toggleShell() {
  const p = $("shellPanel");
  p.hidden = !p.hidden;
  if (!p.hidden) {
    renderShell();
    $("shellInput").focus();
  }
}

async function renderShell() {
  let data;
  try {
    data = await api("/api/shell/history");
  } catch (_err) {
    return;
  }
  const out = $("shellOutput");
  out.innerHTML = "";
  if (!data.commands.length) {
    out.textContent = "No commands yet.";
    return;
  }
  for (const c of data.commands) {
    const row = document.createElement("div");
    row.className = "shell-cmd " + c.source;
    const head = document.createElement("div");
    head.className = "shell-cmd-head";
    head.textContent =
      `[${c.source}] $ ${c.command}` + (c.status === "running" ? "  (running)" : "");
    row.appendChild(head);
    if (c.output) {
      const pre = document.createElement("pre");
      pre.className = "shell-cmd-out";
      pre.textContent = c.output;
      row.appendChild(pre);
    }
    out.appendChild(row);
  }
  out.scrollTop = out.scrollHeight;
}

async function runShell() {
  const cmd = $("shellInput").value.trim();
  if (!cmd) return;
  $("shellInput").value = "";
  postJson("/api/shell/run", { command: cmd }).catch(() => {});
  await renderShell();
  // poll until the command finishes
  for (let i = 0; i < 240; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const d = await api("/api/shell/history").catch(() => null);
    if (!d || !d.commands.some((c) => c.status === "running")) {
      await renderShell();
      break;
    }
  }
}

/* ---------- settings ---------- */

async function openSettings() {
  if (window.njuagentAPI) {
    const st = await window.njuagentAPI.keyStatus();
    $("apiKeyStatus").textContent = st.set ? "API key is set." : "No API key set.";
  } else {
    $("apiKeyStatus").textContent =
      "Set the API key in the app Settings (Electron) or via DEEPSEEK_API_KEY.";
  }
  $("apiKeyInput").value = "";
  $("settingsModal").hidden = false;
}

/* ---------- resizable panes ---------- */

function initResizers() {
  const main = document.querySelector("main");
  let dragging = null;
  document.querySelectorAll(".resizer").forEach((rz) => {
    rz.addEventListener("pointerdown", (e) => {
      dragging = {
        side: rz.dataset.side,
        startX: e.clientX,
        startTree: parseFloat(getComputedStyle(main).getPropertyValue("--tree-w")) || 240,
        startChat: parseFloat(getComputedStyle(main).getPropertyValue("--chat-w")) || 400,
      };
      rz.classList.add("active");
      rz.setPointerCapture(e.pointerId);
    });
    rz.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - dragging.startX;
      if (dragging.side === "left") {
        main.style.setProperty("--tree-w", Math.max(120, dragging.startTree + dx) + "px");
      } else {
        main.style.setProperty("--chat-w", Math.max(220, dragging.startChat - dx) + "px");
      }
    });
    const end = () => {
      dragging = null;
      rz.classList.remove("active");
    };
    rz.addEventListener("pointerup", end);
    rz.addEventListener("pointercancel", end);
  });
}

async function refreshCurrentFile() {
  if (state.currentPath) await openFile(state.currentPath);
}

/* ---------- sidebar tabs ---------- */

function switchTab(tab) {
  document.querySelectorAll(".sidebar-tabs .tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
  });
  $("filesView").hidden = tab !== "files";
  $("gitView").hidden = tab !== "git";
  $("searchView").hidden = tab !== "search";
}

/* ---------- git view ---------- */

async function renderGit() {
  const content = $("gitContent");
  let status;
  try {
    status = await api("/api/git/status");
  } catch (err) {
    content.textContent = "Git error: " + err.message;
    return;
  }
  content.innerHTML = "";
  if (!status.initialized) {
    const p = document.createElement("p");
    p.className = "git-empty";
    p.textContent = "This folder is not a git repository.";
    const init = document.createElement("button");
    init.className = "git-init";
    init.textContent = "Initialize Repository";
    init.onclick = async () => {
      try {
        await postJson("/api/git/init", {});
        renderGit();
      } catch (err) {
        content.textContent = "Git error: " + err.message;
      }
    };
    content.append(p, init);
    return;
  }
  const msg = document.createElement("input");
  msg.className = "git-message";
  msg.placeholder = "Commit message";
  const commit = document.createElement("button");
  commit.className = "git-commit";
  commit.textContent = "Commit";
  commit.onclick = async () => {
    try {
      await postJson("/api/git/commit", { message: msg.value });
      msg.value = "";
      renderGit();
    } catch (err) {
      content.textContent = "Git error: " + err.message;
    }
  };
  content.append(msg, commit);
  const head = document.createElement("div");
  head.className = "git-head";
  head.textContent = status.branch ? `branch: ${status.branch}` : "branch: (none)";
  content.append(head);
  const list = document.createElement("div");
  list.className = "git-changes";
  if (status.changes.length === 0) {
    const empty = document.createElement("div");
    empty.className = "git-empty";
    empty.textContent = "No changes";
    list.append(empty);
  } else {
    for (const c of status.changes) {
      const row = document.createElement("div");
      row.className = "git-change";
      const st = document.createElement("span");
      st.className = "git-status";
      st.textContent = c.status;
      const path = document.createElement("span");
      path.className = "git-path";
      path.textContent = c.path;
      path.title = c.path;
      row.append(st, path);
      list.append(row);
    }
  }
  content.append(list);
}

/* ---------- search view ---------- */

async function doSearch() {
  const query = $("searchQuery").value.trim();
  const resultsEl = $("searchResults");
  resultsEl.innerHTML = "";
  if (!query) return;
  const opts = state.searchOpts;
  let data;
  try {
    data = await api(
      `/api/search?query=${encodeURIComponent(query)}` +
      `&case_sensitive=${opts.case}` +
      `&whole_word=${opts.word}` +
      `&regex=${opts.regex}`
    );
  } catch (err) {
    resultsEl.textContent = "Search error: " + err.message;
    return;
  }
  if (data.results.length === 0) {
    resultsEl.textContent = "No results";
    return;
  }
  for (const f of data.results) {
    const file = document.createElement("div");
    file.className = "search-file";
    const fileHead = document.createElement("div");
    fileHead.className = "search-file-head";
    fileHead.textContent = f.path;
    fileHead.onclick = () => openFile(f.path);
    file.append(fileHead);
    const details = document.createElement("div");
    details.className = "search-matches";
    for (const m of f.matches) {
      const mrow = document.createElement("div");
      mrow.className = "search-match";
      const lineNo = document.createElement("span");
      lineNo.className = "search-line";
      lineNo.textContent = m.line;
      const text = document.createElement("span");
      text.className = "search-text";
      text.textContent = m.text;
      mrow.append(lineNo, text);
      mrow.onclick = () => openFile(f.path);
      details.append(mrow);
    }
    file.append(details);
    resultsEl.append(file);
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
    ok.textContent = "Keep";
    ok.title = "Accept changes";
    const x = document.createElement("button");
    x.className = "p-rollback";
    x.textContent = "Rollback";
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
  await renderTree();
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
      await postJson("/api/file", { path: state.currentPath, content: editorCM.getValue() });
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
  document.querySelectorAll(".sidebar-tabs .tab").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });
  $("searchBtn").addEventListener("click", doSearch);
  $("searchQuery").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });
  document.querySelectorAll("#searchOpts .opt").forEach((b) => {
    b.addEventListener("click", () => {
      const key = b.dataset.opt;
      state.searchOpts[key] = !state.searchOpts[key];
      b.classList.toggle("active", state.searchOpts[key]);
    });
  });
  initResizers();
  initTreeOps();
  $("settingsBtn").addEventListener("click", openSettings);
  $("settingsClose").addEventListener("click", () => {
    $("settingsModal").hidden = true;
  });
  $("shellForm").addEventListener("submit", (e) => {
    e.preventDefault();
    runShell();
  });
  $("shellStop").addEventListener("click", async () => {
    await postJson("/api/shell/stop", {}).catch(console.error);
    await renderShell();
  });
  $("shellClose").addEventListener("click", () => {
    $("shellPanel").hidden = true;
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "`" && e.ctrlKey) {
      e.preventDefault();
      toggleShell();
    }
  });
  $("apiKeySave").addEventListener("click", async () => {
    const key = $("apiKeyInput").value.trim();
    if (!key) return;
    if (window.njuagentAPI) {
      await window.njuagentAPI.setKey(key);
      $("settingsModal").hidden = true;
    } else {
      $("apiKeyStatus").textContent =
        "Setting the API key requires the Electron app.";
    }
  });
  initEditor();

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
    renderGit();
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
  highlightBlocks(box);
  box.scrollTop = box.scrollHeight;
}

window.addEventListener("DOMContentLoaded", init);
