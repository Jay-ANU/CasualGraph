const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktopAPI", {
  platform: process.platform,
  versions: process.versions,
  apiRequest: (payload) => ipcRenderer.invoke("api:request", payload),
  uploadFile: (payload) => ipcRenderer.invoke("api:uploadFile", payload),
  captureScreen: () => ipcRenderer.invoke("screen:capture"),
  openExternal: (url) => ipcRenderer.invoke("shell:openExternal", url),
  setMode: (mode) => ipcRenderer.invoke("window:setMode", mode),
  minimize: () => ipcRenderer.invoke("window:minimize"),
  close: () => ipcRenderer.invoke("window:close")
});
