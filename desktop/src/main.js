const { app, BrowserWindow, desktopCapturer, ipcMain, screen, shell } = require("electron");
const fs = require("fs");
const path = require("path");

const DEFAULT_API_BASE = "https://casualgraph.fly.dev";
const WINDOW_MODES = {
  dock: { width: 82, height: 82, minWidth: 82, minHeight: 82 },
  pet: { width: 384, height: 158, minWidth: 348, minHeight: 138 },
  work: { width: 430, height: 620, minWidth: 360, minHeight: 520 },
  chat: { width: 430, height: 620, minWidth: 360, minHeight: 520 }
};

let mainWindow = null;
let currentWindowMode = "dock";

function createWindow() {
  mainWindow = new BrowserWindow({
    width: WINDOW_MODES.dock.width,
    height: WINDOW_MODES.dock.height,
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

  keepWindowAboveCurrentWorkspace(mainWindow);
  snapDockWindowToEdge(mainWindow, WINDOW_MODES.dock, { preferredEdge: "right", centerVertically: true });
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

async function handleFileUpload(_event, payload) {
  const request = payload || {};
  const file = request.file || {};
  const filePath = String(file.path || "");
  if (!filePath) {
    throw new Error("Missing file path for desktop upload.");
  }

  const headers = {};
  appendSafeHeaders(headers, request.headers);
  if (request.token) {
    headers.authorization = `Bearer ${request.token}`;
  }

  const form = new FormData();
  const fields = request.fields || {};
  for (const [key, value] of Object.entries(fields)) {
    form.append(key, value == null ? "" : String(value));
  }

  const buffer = await fs.promises.readFile(filePath);
  const blob = new Blob([buffer], {
    type: String(file.type || "application/octet-stream")
  });
  form.append("file", blob, String(file.name || path.basename(filePath) || "upload.bin"));

  const response = await fetch(buildApiUrl(request.baseUrl, request.path || "/documents/upload-async"), {
    method: "POST",
    headers,
    body: form
  });
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
  registerDisplayTracking();
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
ipcMain.handle("api:uploadFile", handleFileUpload);

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function keepWindowAboveCurrentWorkspace(win) {
  if (!win || win.isDestroyed()) {
    return;
  }
  if (process.platform === "darwin") {
    win.setAlwaysOnTop(true, "screen-saver");
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    win.setFullScreenable(false);
  } else {
    win.setAlwaysOnTop(true, "floating");
  }
  if (typeof win.moveTop === "function") {
    win.moveTop();
  }
}

function reanchorWindowToVisibleWorkArea() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  keepWindowAboveCurrentWorkspace(mainWindow);
  const target = WINDOW_MODES[currentWindowMode] || WINDOW_MODES.dock;
  if (currentWindowMode === "dock") {
    snapDockWindowToEdge(mainWindow, target);
  } else {
    positionExpandedWindowInWorkArea(mainWindow, target);
  }
}

function registerDisplayTracking() {
  const reanchorSoon = () => setTimeout(reanchorWindowToVisibleWorkArea, 120);
  screen.on("display-metrics-changed", reanchorSoon);
  screen.on("display-added", reanchorSoon);
  screen.on("display-removed", reanchorSoon);
}

function snapDockWindowToEdge(win, target, options = {}) {
  if (!win || win.isDestroyed()) {
    return;
  }
  const bounds = win.getBounds();
  const display = screen.getDisplayMatching(bounds);
  const workArea = display.workArea;
  const margin = 8;
  const targetWidth = target.width;
  const targetHeight = target.height;
  const centerX = bounds.x + bounds.width / 2;
  const centerY = bounds.y + bounds.height / 2;
  const leftEdge = workArea.x + margin;
  const rightEdge = workArea.x + workArea.width - target.width - margin;
  const preferredEdge = options.preferredEdge;
  const x = preferredEdge === "right" || (!preferredEdge && centerX >= workArea.x + workArea.width / 2)
    ? rightEdge
    : leftEdge;
  const unclampedY = options.centerVertically
    ? workArea.y + (workArea.height - targetHeight) / 2
    : centerY - targetHeight / 2;
  const y = clamp(
    Math.round(unclampedY),
    workArea.y + margin,
    workArea.y + workArea.height - targetHeight - margin
  );
  win.setBounds({
    x: Math.round(x),
    y,
    width: targetWidth,
    height: targetHeight
  }, true);
}

function positionExpandedWindowInWorkArea(win, target, previousBounds) {
  if (!win || win.isDestroyed()) {
    return;
  }
  const display = screen.getDisplayMatching(previousBounds || win.getBounds());
  const workArea = display.workArea;
  const margin = 8;
  const anchorBounds = previousBounds || win.getBounds();
  const previousCenterX = anchorBounds.x + anchorBounds.width / 2;
  const previousCenterY = anchorBounds.y + anchorBounds.height / 2;
  const rightAlignedX = workArea.x + workArea.width - target.width - margin;
  const leftAlignedX = workArea.x + margin;
  const x = previousCenterX >= workArea.x + workArea.width / 2
    ? rightAlignedX
    : leftAlignedX;
  const y = clamp(
    Math.round(previousCenterY - target.height / 2),
    workArea.y + margin,
    workArea.y + workArea.height - target.height - margin
  );
  win.setBounds({
    x: Math.round(x),
    y,
    width: target.width,
    height: target.height
  }, true);
}

ipcMain.handle("window:setMode", (event, mode) => {
  const win = getSenderWindow(event);
  const normalized = Object.prototype.hasOwnProperty.call(WINDOW_MODES, mode) ? mode : "work";
  const target = WINDOW_MODES[normalized];
  if (!win) {
    return normalized;
  }
  currentWindowMode = normalized;
  const previousBounds = win.getBounds();
  win.setMinimumSize(target.minWidth, target.minHeight);
  if (normalized === "dock") {
    snapDockWindowToEdge(win, target);
  } else {
    positionExpandedWindowInWorkArea(win, target, previousBounds);
  }
  keepWindowAboveCurrentWorkspace(win);
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
      keepWindowAboveCurrentWorkspace(win);
      reanchorWindowToVisibleWorkArea();
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
