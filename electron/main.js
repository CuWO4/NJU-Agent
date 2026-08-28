// njuagent Electron shell.
//
// Spawns the Python backend (the existing FastAPI server) on a free port and
// loads its Web UI in a native window. One backend process == one workspace.
// Without a workspace the window shows a local welcome page; opening/switching
// a workspace (File menu or the welcome button) kills the previous backend
// (if any) and starts a fresh one for the chosen directory.
//
// Dev mode: backend runs from source via `python -m njuagent.cli <dir>
// --port N --no-browser`. Packaged mode (PyInstaller exe under
// resources/python): backend is launched as a standalone executable.

const { app, BrowserWindow, shell, dialog, ipcMain, Menu } = require("electron");
const { spawn, execFile } = require("child_process");
const { promisify } = require("util");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");

const execFileAsync = promisify(execFile);

const isPackaged = app.isPackaged;
const sourceDir = path.join(__dirname, "..");

const pythonCmd = isPackaged
  ? path.join(process.resourcesPath, "python", "njuagent.exe")
  : process.env.NJUAGENT_PYTHON || "python";

let backendProc = null;
let win = null;

// App data dir: where njuagent-config.json (API key) lives. Packaged mode
// uses the folder of the portable exe; dev mode uses the source tree.
function appDataDir() {
  return isPackaged ? path.dirname(contextMenuTarget()) : sourceDir;
}

function readAppConfig() {
  try {
    const raw = fs.readFileSync(path.join(appDataDir(), "njuagent-config.json"), "utf-8");
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : {};
  } catch (_err) {
    return {};
  }
}

function writeAppConfig(obj) {
  fs.mkdirSync(appDataDir(), { recursive: true });
  fs.writeFileSync(
    path.join(appDataDir(), "njuagent-config.json"),
    JSON.stringify(obj, null, 2),
    "utf-8"
  );
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on("error", reject);
  });
}

function waitForServer(port) {
  return new Promise((resolve) => {
    const tryOnce = () => {
      http
        .get(`http://127.0.0.1:${port}/`, (res) => {
          res.resume();
          resolve();
        })
        .on("error", () => setTimeout(tryOnce, 200));
    };
    tryOnce();
  });
}

function startBackend(workdir) {
  return new Promise(async (resolve, reject) => {
    const port = await findFreePort();
    const args = [
      ...(isPackaged ? [workdir] : ["-m", "njuagent.cli", workdir]),
      "--port", String(port),
      "--no-browser",
    ];
    backendProc = spawn(pythonCmd, args, {
      cwd: isPackaged ? workdir : sourceDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        NJUAGENT_API_KEY: readAppConfig().api_key || "",
        NJUAGENT_PORT: String(port),
      },
    });
    backendProc.stdout.on("data", (d) => console.log("[backend]", d.toString().trim()));
    backendProc.stderr.on("data", (d) => console.log("[backend]", d.toString().trim()));
    backendProc.on("exit", (code) => console.log("[backend] exited", code));
    backendProc.on("error", reject);
    try {
      await waitForServer(port);
      resolve(port);
    } catch (err) {
      reject(err);
    }
  });
}

function stopBackend() {
  if (backendProc) {
    backendProc.kill();
    backendProc = null;
  }
}

async function openWorkspace(dir) {
  if (isPackaged && !readAppConfig().api_key) {
    dialog.showMessageBox(win, {
      type: "info",
      title: "njuagent",
      message: "No API key set",
      detail: "Set your DeepSeek API key in Settings before opening a workspace.",
    });
    return false;
  }
  stopBackend();
  const port = await startBackend(dir);
  if (win) win.loadURL(`http://127.0.0.1:${port}/`);
  return true;
}

function closeWorkspace() {
  stopBackend();
  if (win) win.loadFile(path.join(__dirname, "welcome.html"));
}

async function chooseWorkspace() {
  if (!win) return false;
  const res = await dialog.showOpenDialog(win, {
    title: "Open Workspace",
    properties: ["openDirectory"],
  });
  if (res.canceled || res.filePaths.length === 0) return false;
  try {
    await openWorkspace(res.filePaths[0]);
    return true;
  } catch (err) {
    console.error("[workspace] failed to start backend:", err);
    return false;
  }
}

function buildMenu() {
  const template = [
    {
      label: "File",
      submenu: [
        {
          label: "Open Workspace...",
          accelerator: "CmdOrCtrl+O",
          click: () => chooseWorkspace(),
        },
        { label: "Close Workspace", click: closeWorkspace },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    { role: "editMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

ipcMain.handle("open-workspace", async () => chooseWorkspace());

// --- API key (app-level config, stored in the release/app dir) ---

ipcMain.handle("key-status", () => ({
  set: Boolean(readAppConfig().api_key),
}));
ipcMain.handle("set-key", (_e, key) => {
  const cfg = readAppConfig();
  cfg.api_key = String(key || "").trim();
  writeAppConfig(cfg);
  return { ok: true };
});

// --- Windows "Open njuagent here" context-menu integration ---
// Registered/removed from the Settings panel on the welcome page.

const CTX_KEY = "HKCU\\Software\\Classes\\Directory\\Background\\shell\\njuagent";

function contextMenuTarget() {
  return process.env.PORTABLE_EXECUTABLE_FILE || process.execPath;
}

async function contextMenuInstalled() {
  try {
    await execFileAsync("reg", ["query", CTX_KEY]);
    return true;
  } catch (_err) {
    return false;
  }
}

async function installContextMenu() {
  const target = contextMenuTarget();
  await execFileAsync("reg", [
    "add", CTX_KEY, "/ve", "/d", "Open njuagent here", "/f",
  ]);
  await execFileAsync("reg", [
    "add", `${CTX_KEY}\\command`, "/ve", "/d", `"${target}" "%V"`, "/f",
  ]);
}

async function uninstallContextMenu() {
  try {
    await execFileAsync("reg", ["delete", CTX_KEY, "/f"]);
  } catch (_err) {
    // key absent; nothing to do
  }
}

ipcMain.handle("context-menu-status", async () => contextMenuInstalled());
ipcMain.handle("context-menu-install", async () => {
  try {
    await installContextMenu();
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
});
ipcMain.handle("context-menu-uninstall", async () => {
  try {
    await uninstallContextMenu();
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
});

app.whenReady().then(() => {
  buildMenu();
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    backgroundColor: "#1e1e1e",
    title: "njuagent",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "welcome.html"));
  win.on("closed", () => {
    win = null;
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("quit", () => {
  stopBackend();
});
