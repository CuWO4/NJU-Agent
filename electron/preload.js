// Preload: expose a minimal bridge to the welcome page (context-isolated).
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("njuagentAPI", {
  openWorkspace: () => ipcRenderer.invoke("open-workspace"),
  contextMenuStatus: () => ipcRenderer.invoke("context-menu-status"),
  contextMenuInstall: () => ipcRenderer.invoke("context-menu-install"),
  contextMenuUninstall: () => ipcRenderer.invoke("context-menu-uninstall"),
  keyStatus: () => ipcRenderer.invoke("key-status"),
  setKey: (key) => ipcRenderer.invoke("set-key", key),
});
