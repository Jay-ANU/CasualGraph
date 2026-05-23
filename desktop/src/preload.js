const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktopAPI", {
  platform: process.platform,
  versions: process.versions,
  apiBase: process.env.CASUALGRAPH_API_BASE || "https://casualgraph.fly.dev",
  apiRequest: (payload) => ipcRenderer.invoke("api:request", payload),
  uploadFile: (payload) => ipcRenderer.invoke("api:uploadFile", payload),
  saveBase64File: (payload) => ipcRenderer.invoke("file:saveBase64", payload),
  captureScreen: () => ipcRenderer.invoke("screen:capture"),
  openExternal: (url) => ipcRenderer.invoke("shell:openExternal", url),
  setMode: (mode) => ipcRenderer.invoke("window:setMode", mode),
  minimize: () => ipcRenderer.invoke("window:minimize"),
  close: () => ipcRenderer.invoke("window:close")
});
