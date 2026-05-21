const { app, BrowserWindow, desktopCapturer, ipcMain, shell } = require("electron");
const path = require("path");

const DEFAULT_API_BASE = "https://casualgraph.fly.dev";

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 380,
    height: 560,
    minWidth: 330,
    minHeight: 460,
    frame: false,
    transparent: true,
    resizable: true,
    alwaysOnTop: true,
    backgroundColor: "#00000000",
    title: "CausalGraph Pet",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.setAlwaysOnTop(true, "floating");
  mainWindow.loadFile(path.join(__dirname, "index.html"));
}

function getSenderWindow(event) {
  return BrowserWindow.fromWebContents(event.sender);
}

function buildApiUrl(baseUrl, apiPath) {
  const parsed = new URL(String(baseUrl || DEFAULT_API_BASE).trim());
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("API base must start with http:// or https://");
  }
  const pathValue = String(apiPath || "/").replace(/^\/+/, "");
  return new URL(pathValue, `${parsed.origin}/`).toString();
}

function appendSafeHeaders(headers, extraHeaders) {
  for (const [key, value] of Object.entries(extraHeaders || {})) {
    const normalized = String(key || "").trim().toLowerCase();
    if (!normalized || normalized === "host" || normalized === "content-length") {
      continue;
    }
    headers[normalized] = String(value);
  }
}

function buildFileBuffer(filePayload) {
  const bytes = filePayload && filePayload.bytes;
  if (bytes instanceof ArrayBuffer) {
    return Buffer.from(bytes);
  }
  if (ArrayBuffer.isView(bytes)) {
    return Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  }
  if (Array.isArray(bytes)) {
    return Buffer.from(bytes);
  }
  return Buffer.alloc(0);
}

async function handleApiRequest(_event, payload) {
  const request = payload || {};
  const headers = {};
  appendSafeHeaders(headers, request.headers);
  if (request.token) {
    headers.authorization = `Bearer ${request.token}`;
  }

  const options = {
    method: String(request.method || "GET").toUpperCase(),
    headers
  };

  if (request.formData) {
    const form = new FormData();
    const fields = request.formData.fields || {};
    for (const [key, value] of Object.entries(fields)) {
      form.append(key, value == null ? "" : String(value));
    }
    if (request.formData.file) {
      const file = request.formData.file;
      const buffer = buildFileBuffer(file);
      const blob = new Blob([buffer], {
        type: String(file.type || "application/octet-stream")
      });
      form.append("file", blob, String(file.name || "upload.bin"));
    }
    options.body = form;
  } else if (Object.prototype.hasOwnProperty.call(request, "json")) {
    headers["content-type"] = "application/json";
    options.body = JSON.stringify(request.json);
  }

  const response = await fetch(buildApiUrl(request.baseUrl, request.path), options);
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (_error) {
      data = null;
    }
  }
  return {
    ok: response.ok,
    status: response.status,
    data,
    text
  };
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

ipcMain.handle("api:request", handleApiRequest);

ipcMain.handle("screen:capture", async () => {
  const sources = await desktopCapturer.getSources({
    types: ["screen"],
    thumbnailSize: { width: 1440, height: 900 }
  });
  const source = sources[0];
  if (!source) {
    throw new Error("No screen source is available");
  }
  return {
    id: source.id,
    name: source.name,
    dataUrl: source.thumbnail.toDataURL()
  };
});

ipcMain.handle("shell:openExternal", async (_event, url) => {
  const target = String(url || "");
  if (!/^https?:\/\//i.test(target)) {
    return false;
  }
  await shell.openExternal(target);
  return true;
});

ipcMain.handle("window:minimize", (event) => {
  const win = getSenderWindow(event);
  if (win) {
    win.minimize();
  }
});

ipcMain.handle("window:close", (event) => {
  const win = getSenderWindow(event);
  if (win) {
    win.close();
  }
});
