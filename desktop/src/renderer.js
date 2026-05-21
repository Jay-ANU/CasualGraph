const DEFAULT_API_BASE = "https://casualgraph.fly.dev";
const API_BASE_KEY = "causalgraph.pet.apiBase";
const TOKEN_KEY = "causalgraph.pet.token";
const USER_KEY = "causalgraph.pet.user";
const HISTORY_KEY = "causalgraph.pet.history";
const WEB_APP_URL = "https://casualgraphai.vercel.app";

const elements = {
  apiBaseInput: document.getElementById("apiBaseInput"),
  signedOutView: document.getElementById("signedOutView"),
  signedInView: document.getElementById("signedInView"),
  emailInput: document.getElementById("emailInput"),
  passwordInput: document.getElementById("passwordInput"),
  loginButton: document.getElementById("loginButton"),
  logoutButton: document.getElementById("logoutButton"),
  userLabel: document.getElementById("userLabel"),
  dropZone: document.getElementById("dropZone"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  progressTrack: document.getElementById("progressTrack"),
  progressBar: document.getElementById("progressBar"),
  captureButton: document.getElementById("captureButton"),
  openWebButton: document.getElementById("openWebButton"),
  screenshotPanel: document.getElementById("screenshotPanel"),
  screenshotPreview: document.getElementById("screenshotPreview"),
  screenshotPrompt: document.getElementById("screenshotPrompt"),
  summarizeScreenButton: document.getElementById("summarizeScreenButton"),
  chatLog: document.getElementById("chatLog"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  sendButton: document.getElementById("sendButton"),
  minimizeButton: document.getElementById("minimizeButton"),
  closeButton: document.getElementById("closeButton")
};

let token = localStorage.getItem(TOKEN_KEY) || "";
let currentUser = readJson(USER_KEY, null);
let messages = readJson(HISTORY_KEY, []);
let currentScreenshot = null;
let busy = false;

function readJson(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch (_error) {
    return fallback;
  }
}

function saveJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function apiBase() {
  return (elements.apiBaseInput.value || DEFAULT_API_BASE).trim().replace(/\/+$/, "");
}

function setBusy(nextBusy, label) {
  busy = nextBusy;
  elements.loginButton.disabled = busy;
  elements.sendButton.disabled = busy;
  elements.captureButton.disabled = busy;
  elements.summarizeScreenButton.disabled = busy;
  elements.statusDot.classList.toggle("busy", busy);
  if (label) {
    elements.statusText.textContent = label;
  }
}

function setStatus(message, tone = "ready") {
  elements.statusText.textContent = message;
  elements.statusDot.classList.toggle("error", tone === "error");
  elements.statusDot.classList.toggle("busy", tone === "busy");
}

function setProgress(value) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  elements.progressTrack.classList.toggle("hidden", percent <= 0 || percent >= 100);
  elements.progressBar.style.width = `${percent}%`;
}

function extractError(response) {
  const data = response && response.data;
  if (data && data.detail && typeof data.detail === "object") {
    return data.detail.message || data.detail.error || JSON.stringify(data.detail);
  }
  if (data && typeof data.detail === "string") {
    return data.detail;
  }
  if (data && (data.message || data.error)) {
    return data.message || data.error;
  }
  return (response && response.text) || `Request failed with status ${response && response.status}`;
}

async function apiRequest(path, options = {}) {
  if (!window.desktopAPI || !window.desktopAPI.apiRequest) {
    throw new Error("Desktop bridge is unavailable");
  }
  const payload = {
    baseUrl: apiBase(),
    path,
    method: options.method || "GET",
    token: options.token === null ? "" : token,
    headers: options.headers || {}
  };
  if (Object.prototype.hasOwnProperty.call(options, "json")) {
    payload.json = options.json;
  }
  if (Object.prototype.hasOwnProperty.call(options, "formData")) {
    payload.formData = options.formData;
  }
  const response = await window.desktopAPI.apiRequest(payload);
  if (!response.ok) {
    throw new Error(extractError(response));
  }
  return response.data;
}

function requireAuth() {
  if (!token) {
    throw new Error("Sign in first");
  }
}

function renderAuth() {
  const signedIn = Boolean(token && currentUser);
  elements.signedOutView.classList.toggle("hidden", signedIn);
  elements.signedInView.classList.toggle("hidden", !signedIn);
  if (signedIn) {
    elements.userLabel.textContent = currentUser.email || currentUser.username || "Signed in";
  }
}

function addMessage(role, text) {
  const item = {
    role,
    text: String(text || ""),
    createdAt: new Date().toISOString()
  };
  messages.push(item);
  messages = messages.slice(-40);
  saveJson(HISTORY_KEY, messages);
  renderMessages();
}

function renderMessages() {
  elements.chatLog.innerHTML = "";
  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "message system";
    empty.textContent = "Drop files here or ask a question from the pet window.";
    elements.chatLog.appendChild(empty);
  } else {
    for (const message of messages) {
      const node = document.createElement("div");
      node.className = `message ${message.role}`;
      node.textContent = message.text;
      elements.chatLog.appendChild(node);
    }
  }
  requestAnimationFrame(() => {
    elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
  });
}

async function handleLogin() {
  const email = elements.emailInput.value.trim();
  const password = elements.passwordInput.value;
  if (!email || !password) {
    setStatus("Email and password are required", "error");
    return;
  }
  try {
    setBusy(true, "Signing in");
    const data = await apiRequest("/auth/login", {
      method: "POST",
      token: null,
      json: { email, password }
    });
    token = data.token || "";
    currentUser = data.user || null;
    localStorage.setItem(TOKEN_KEY, token);
    saveJson(USER_KEY, currentUser);
    renderAuth();
    setStatus("Signed in");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
}

function handleLogout() {
  token = "";
  currentUser = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  renderAuth();
  setStatus("Signed out");
}

async function uploadFile(file) {
  requireAuth();
  if (!file) {
    return;
  }
  setBusy(true, `Uploading ${file.name}`);
  setProgress(4);
  const bytes = Array.from(new Uint8Array(await file.arrayBuffer()));
  const job = await apiRequest("/documents/upload-async", {
    method: "POST",
    formData: {
      fields: {
        title: file.name,
        domain: "desktop",
        source: "desktop-pet",
        source_type: "desktop_file",
        content: ""
      },
      file: {
        name: file.name,
        type: file.type || "application/octet-stream",
        bytes
      }
    }
  });

  const jobId = job.job_id;
  if (!jobId) {
    setStatus("Upload accepted");
    setProgress(100);
    return;
  }
  await pollUploadJob(jobId);
}

async function pollUploadJob(jobId) {
  for (;;) {
    await wait(1200);
    const job = await apiRequest(`/documents/jobs/${jobId}`);
    setProgress(job.progress || 0);
    setStatus(job.message || job.status || "Processing", "busy");
    if (["completed", "failed", "rejected"].includes(job.status)) {
      setProgress(100);
      if (job.status === "completed") {
        setStatus("Document is ready");
        addMessage("system", `Uploaded: ${job.result && job.result.title ? job.result.title : "document"}`);
      } else {
        throw new Error(job.error || job.message || "Document processing failed");
      }
      break;
    }
  }
}

async function sendChat(question) {
  requireAuth();
  const trimmed = String(question || "").trim();
  if (!trimmed) {
    return;
  }
  const history = messages
    .slice(-10)
    .filter((item) => item.role === "user" || item.role === "assistant")
    .map((item) => ({ role: item.role, content: item.text }));
  addMessage("user", trimmed);
  setBusy(true, "Thinking");
  const data = await apiRequest("/rag/ask", {
    method: "POST",
    json: {
      question: trimmed,
      top_k: 5,
      history,
      reasoning_mode: "flash"
    }
  });
  addMessage("assistant", data.answer || "No answer returned.");
  setStatus("Ready");
}

async function captureScreen() {
  requireAuth();
  setBusy(true, "Capturing screen");
  const capture = await window.desktopAPI.captureScreen();
  currentScreenshot = capture.dataUrl;
  elements.screenshotPreview.src = currentScreenshot;
  elements.screenshotPanel.classList.remove("hidden");
  if (!elements.screenshotPrompt.value.trim()) {
    elements.screenshotPrompt.value = "Summarize the visible information and point out anything that needs attention.";
  }
  setStatus(`Captured ${capture.name || "screen"}`);
}

async function summarizeScreenshot() {
  requireAuth();
  if (!currentScreenshot) {
    await captureScreen();
  }
  const prompt = elements.screenshotPrompt.value.trim() || "Summarize this screen.";
  addMessage("user", "Summarize my current screen.");
  setBusy(true, "Summarizing screenshot");
  const data = await apiRequest("/desktop/screenshot/summarize", {
    method: "POST",
    json: {
      image_data_url: currentScreenshot,
      prompt
    }
  });
  addMessage("assistant", data.summary || "No screenshot summary returned.");
  setStatus("Ready");
}

function handleDrop(event) {
  event.preventDefault();
  elements.dropZone.classList.remove("dragging");
  const files = Array.from(event.dataTransfer.files || []);
  if (!files.length) {
    return;
  }
  uploadFile(files[0]).catch((error) => {
    setStatus(error.message, "error");
  }).finally(() => {
    setBusy(false);
    setProgress(100);
  });
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function bindEvents() {
  elements.apiBaseInput.addEventListener("change", () => {
    localStorage.setItem(API_BASE_KEY, apiBase());
  });
  elements.loginButton.addEventListener("click", handleLogin);
  elements.logoutButton.addEventListener("click", handleLogout);
  elements.passwordInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      handleLogin();
    }
  });
  elements.dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("dragging");
  });
  elements.dropZone.addEventListener("dragleave", () => {
    elements.dropZone.classList.remove("dragging");
  });
  elements.dropZone.addEventListener("drop", handleDrop);
  elements.chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = elements.chatInput.value;
    elements.chatInput.value = "";
    sendChat(question).catch((error) => {
      setStatus(error.message, "error");
    }).finally(() => {
      setBusy(false);
    });
  });
  elements.captureButton.addEventListener("click", () => {
    captureScreen().catch((error) => {
      setStatus(error.message, "error");
    }).finally(() => {
      setBusy(false);
    });
  });
  elements.summarizeScreenButton.addEventListener("click", () => {
    summarizeScreenshot().catch((error) => {
      setStatus(error.message, "error");
    }).finally(() => {
      setBusy(false);
    });
  });
  elements.openWebButton.addEventListener("click", () => {
    window.desktopAPI.openExternal(WEB_APP_URL);
  });
  elements.minimizeButton.addEventListener("click", () => {
    window.desktopAPI.minimize();
  });
  elements.closeButton.addEventListener("click", () => {
    window.desktopAPI.close();
  });
}

function init() {
  elements.apiBaseInput.value = localStorage.getItem(API_BASE_KEY) || DEFAULT_API_BASE;
  renderAuth();
  renderMessages();
  bindEvents();
}

init();
