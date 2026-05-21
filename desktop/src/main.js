const { app, BrowserWindow, desktopCapturer, ipcMain, shell } = require("electron");
const path = require("path");

const DEFAULT_API_BASE = "https://casualgraph.fly.dev";
const WINDOW_MODES = {
  dock: { width: 82, height: 82, minWidth: 82, minHeight: 82 },
  pet: { width: 384, height: 158, minWidth: 348, minHeight: 138 },
  work: { width: 430, height: 620, minWidth: 360, minHeight: 520 },
  chat: { width: 430, height: 620, minWidth: 360, minHeight: 520 }
};

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: WINDOW_MODES.pet.width,
    height: WINDOW_MODES.pet.height,
    minWidth: WINDOW_MODES.dock.minWidth,
    minHeight: WINDOW_MODES.dock.minHeight,
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

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
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

ipcMain.handle("window:setMode", (event, mode) => {
  const win = getSenderWindow(event);
  const normalized = Object.prototype.hasOwnProperty.call(WINDOW_MODES, mode) ? mode : "work";
  const target = WINDOW_MODES[normalized];
  if (!win) {
    return normalized;
  }
  win.setMinimumSize(target.minWidth, target.minHeight);
  win.setSize(target.width, target.height, true);
  return normalized;
});

async function captureScreenWithoutWindow(win) {
  const shouldRestore = Boolean(win && !win.isDestroyed() && win.isVisible());
  if (shouldRestore) {
    win.hide();
    await wait(260);
  }

  try {
    let source = null;
    for (let attempt = 0; attempt < 2 && !source; attempt += 1) {
      if (attempt > 0) {
        await wait(220);
      }
      const sources = await desktopCapturer.getSources({
        types: ["screen"],
        thumbnailSize: { width: 1440, height: 900 }
      });
      source = sources.find((candidate) => {
        const thumbnail = candidate && candidate.thumbnail;
        return thumbnail && !thumbnail.isEmpty() && thumbnail.toDataURL().length > "data:image/png;base64,".length;
      });
    }
    if (!source) {
      throw new Error(
        "Screen capture returned an empty image. On macOS, enable Screen Recording for CausalGraph Pet in System Settings > Privacy & Security > Screen & System Audio Recording, then restart the app."
      );
    }
    return {
      id: source.id,
      name: source.name,
      dataUrl: source.thumbnail.toDataURL()
    };
  } finally {
    if (shouldRestore && win && !win.isDestroyed()) {
      win.showInactive();
      win.setAlwaysOnTop(true, "floating");
    }
  }
}

ipcMain.handle("screen:capture", async (event) => {
  const win = getSenderWindow(event);
  return captureScreenWithoutWindow(win);
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
