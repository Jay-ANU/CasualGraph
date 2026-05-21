const DEFAULT_API_BASE = "https://casualgraph.fly.dev";
const TOKEN_KEY = "causalgraph.pet.token";
const USER_KEY = "causalgraph.pet.user";
const HISTORY_KEY = "causalgraph.pet.history";
const TIER_KEY = "causalgraph.pet.tier";
const WEB_APP_URL = "https://casualgraphai.vercel.app";

const elements = {
  petView: document.getElementById("petView"),
  panelView: document.getElementById("panelView"),
  petExpandButton: document.getElementById("petExpandButton"),
  petCaptureButton: document.getElementById("petCaptureButton"),
  petUploadButton: document.getElementById("petUploadButton"),
  petTitle: document.getElementById("petTitle"),
  petSubtitle: document.getElementById("petSubtitle"),
  panelTitle: document.getElementById("panelTitle"),
  petModeButton: document.getElementById("petModeButton"),
  closeButton: document.getElementById("closeButton"),
  authPanel: document.getElementById("authPanel"),
  signedOutView: document.getElementById("signedOutView"),
  signedInView: document.getElementById("signedInView"),
  emailInput: document.getElementById("emailInput"),
  passwordInput: document.getElementById("passwordInput"),
  loginButton: document.getElementById("loginButton"),
  logoutButton: document.getElementById("logoutButton"),
  userLabel: document.getElementById("userLabel"),
  workView: document.getElementById("workView"),
  dropZone: document.getElementById("dropZone"),
  captureButton: document.getElementById("captureButton"),
  uploadButton: document.getElementById("uploadButton"),
  openWebButton: document.getElementById("openWebButton"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  progressTrack: document.getElementById("progressTrack"),
  progressBar: document.getElementById("progressBar"),
  contextCard: document.getElementById("contextCard"),
  contextTitle: document.getElementById("contextTitle"),
  contextDetail: document.getElementById("contextDetail"),
  contextPreview: document.getElementById("contextPreview"),
  suggestionPanel: document.getElementById("suggestionPanel"),
  suggestionList: document.getElementById("suggestionList"),
  screenshotPanel: document.getElementById("screenshotPanel"),
  screenshotPrompt: document.getElementById("screenshotPrompt"),
  summarizeScreenButton: document.getElementById("summarizeScreenButton"),
  switchToChatButton: document.getElementById("switchToChatButton"),
  chatView: document.getElementById("chatView"),
  chatContextTitle: document.getElementById("chatContextTitle"),
  backToWorkButton: document.getElementById("backToWorkButton"),
  chatLog: document.getElementById("chatLog"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  sendButton: document.getElementById("sendButton"),
  tierFlashButton: document.getElementById("tierFlashButton"),
  tierDeepButton: document.getElementById("tierDeepButton"),
  fileInput: document.getElementById("fileInput")
};

let token = localStorage.getItem(TOKEN_KEY) || "";
let currentUser = readJson(USER_KEY, null);
let messages = readJson(HISTORY_KEY, []);
let currentScreenshot = null;
let tier = normalizeTier(localStorage.getItem(TIER_KEY));
let busy = false;
let appMode = "pet";
let activeContext = null;

function isSignedIn() {
  return Boolean(token && currentUser);
}

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
  return DEFAULT_API_BASE;
}

function normalizeTier(value) {
  return String(value || "").toLowerCase() === "deep" ? "deep" : "flash";
}

function setTier(nextTier) {
  tier = normalizeTier(nextTier);
  localStorage.setItem(TIER_KEY, tier);
  renderTier();
}

function renderTier() {
  elements.tierFlashButton.classList.toggle("active", tier === "flash");
  elements.tierDeepButton.classList.toggle("active", tier === "deep");
  elements.tierFlashButton.setAttribute("aria-pressed", String(tier === "flash"));
  elements.tierDeepButton.setAttribute("aria-pressed", String(tier === "deep"));
}

function setAppMode(nextMode) {
  const requestedMode = ["pet", "work", "chat"].includes(nextMode) ? nextMode : "work";
  appMode = !isSignedIn() && requestedMode === "pet" ? "work" : requestedMode;
  document.body.className = `mode-${appMode}`;
  elements.panelTitle.textContent = appMode === "chat" ? "Ask" : "Desktop Pet";

  if (window.desktopAPI && window.desktopAPI.setMode) {
    window.desktopAPI.setMode(appMode).catch(() => {});
  }
}

function setBusy(nextBusy, label) {
  busy = nextBusy;
  for (const button of [
    elements.loginButton,
    elements.sendButton,
    elements.captureButton,
    elements.petCaptureButton,
    elements.uploadButton,
    elements.petUploadButton,
    elements.summarizeScreenButton
  ]) {
    button.disabled = busy;
  }
  elements.statusDot.classList.toggle("busy", busy);
  if (label) {
    setStatus(label, "busy");
  }
}

function setStatus(message, tone = "ready") {
  const text = String(message || "Ready");
  elements.statusText.textContent = text;
  elements.petSubtitle.textContent = text;
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
  if (data && Array.isArray(data.detail)) {
    const first = data.detail[0] || {};
    return first.msg || JSON.stringify(data.detail);
  }
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

function isUsableImageDataUrl(value) {
  return /^data:image\/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+$/i.test(String(value || ""));
}

function contextSuggestions(context) {
  if (!context) {
    return [
      "What reports are available in my knowledge base?",
      "Summarize the most important evidence.",
      "What should I inspect next?"
    ];
  }
  if (context.type === "document") {
    return [
      "Summarize this report.",
      "What ESG strategy does it describe?",
      "What causal relationships are supported by the evidence?"
    ];
  }
  if (context.type === "screenshot") {
    return [
      "Summarize the visible evidence.",
      "What should I do next from this screen?",
      "Turn this into interview talking points."
    ];
  }
  return ["Summarize this context.", "What should I ask next?", "Which evidence is strongest?"];
}

function setActiveContext(context) {
  activeContext = context || null;
  renderContext();
  renderSuggestions();
}

function renderContext() {
  if (!activeContext) {
    elements.contextCard.classList.add("hidden");
    elements.chatContextTitle.textContent = "General knowledge base";
    elements.contextPreview.classList.add("hidden");
    elements.contextPreview.removeAttribute("src");
    return;
  }

  elements.contextCard.classList.remove("hidden");
  elements.contextTitle.textContent = activeContext.title || "Current context";
  elements.contextDetail.textContent = activeContext.detail || "";
  elements.chatContextTitle.textContent = activeContext.title || "Current context";

  if (activeContext.preview) {
    elements.contextPreview.src = activeContext.preview;
    elements.contextPreview.classList.remove("hidden");
  } else {
    elements.contextPreview.classList.add("hidden");
    elements.contextPreview.removeAttribute("src");
  }
}

function renderSuggestions() {
  const suggestions = activeContext && activeContext.suggestions
    ? activeContext.suggestions
    : contextSuggestions(activeContext);

  elements.suggestionList.innerHTML = "";
  for (const suggestion of suggestions) {
    const button = document.createElement("button");
    button.className = "suggestion-chip";
    button.type = "button";
    button.textContent = suggestion;
    button.addEventListener("click", () => switchToChat(suggestion));
    elements.suggestionList.appendChild(button);
  }
  elements.suggestionPanel.classList.toggle("hidden", suggestions.length === 0);
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
    setAppMode("work");
    throw new Error("Sign in first");
  }
}

function renderAuth() {
  const signedIn = isSignedIn();
  elements.signedOutView.classList.toggle("hidden", signedIn);
  elements.signedInView.classList.toggle("hidden", !signedIn);
  if (signedIn) {
    elements.userLabel.textContent = currentUser.email || currentUser.username || "Signed in";
  }
  if (!signedIn && appMode === "pet") {
    setAppMode("work");
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
    empty.textContent = "Drop a report, capture the screen, or ask from your knowledge base.";
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

function switchToChat(prefill = "") {
  setAppMode("chat");
  if (prefill) {
    elements.chatInput.value = prefill;
  }
  requestAnimationFrame(() => {
    elements.chatInput.focus();
    elements.chatInput.setSelectionRange(elements.chatInput.value.length, elements.chatInput.value.length);
  });
}

function openFilePicker() {
  setAppMode("work");
  elements.fileInput.click();
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
    setStatus("Ready");
    setAppMode("pet");
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
  setActiveContext(null);
  setStatus("Signed out");
  setAppMode("work");
}

async function uploadFile(file) {
  requireAuth();
  if (!file) {
    return;
  }
  setAppMode("work");
  setBusy(true, `Uploading ${file.name}`);
  setProgress(4);
  try {
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
      const title = file.name || "Document";
      setActiveContext({
        type: "document",
        title,
        detail: "Upload was accepted. Ask about it after processing completes.",
        suggestions: contextSuggestions({ type: "document" })
      });
      setStatus("Upload accepted");
      return;
    }
    await pollUploadJob(jobId, file);
  } finally {
    setBusy(false);
    setProgress(100);
    elements.fileInput.value = "";
  }
}

async function pollUploadJob(jobId, file) {
  for (;;) {
    await wait(1200);
    const job = await apiRequest(`/documents/jobs/${jobId}`);
    setProgress(job.progress || 0);
    setStatus(job.message || job.status || "Processing", "busy");
    if (["completed", "failed", "rejected"].includes(job.status)) {
      if (job.status !== "completed") {
        throw new Error(job.error || job.message || "Document processing failed");
      }

      const result = job.result || {};
      const title = result.title || file.name || "Document";
      const documentId = result.document_id || result.documentId || result.doc_id || result.id || null;
      setActiveContext({
        type: "document",
        title,
        detail: "Document is ready in your private knowledge base.",
        documentId,
        suggestions: contextSuggestions({ type: "document" })
      });
      setStatus("Document is ready");
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

  const payload = {
    question: trimmed,
    top_k: 5,
    history,
    reasoning_mode: tier
  };
  if (activeContext && activeContext.documentId) {
    payload.document_ids = [activeContext.documentId];
  }

  addMessage("user", trimmed);
  switchToChat();
  setBusy(true, `Thinking with ${tier === "deep" ? "Deep" : "Flash"}`);
  const data = await apiRequest("/rag/ask", {
    method: "POST",
    json: payload
  });
  addMessage("assistant", data.answer || "No answer returned.");
  setStatus("Ready");
}

async function captureScreen() {
  requireAuth();
  setAppMode("work");
  setBusy(true, "Capturing screen");
  const capture = await window.desktopAPI.captureScreen();
  if (!isUsableImageDataUrl(capture && capture.dataUrl)) {
    currentScreenshot = null;
    throw new Error("Screen capture returned an empty image. Check macOS Screen Recording permission, then restart the app.");
  }
  currentScreenshot = capture.dataUrl;
  setActiveContext({
    type: "screenshot",
    title: capture.name || "Screen capture",
    detail: "Captured just now. Summarize it, then continue asking from chat.",
    preview: currentScreenshot,
    suggestions: contextSuggestions({ type: "screenshot" })
  });
  elements.screenshotPanel.classList.remove("hidden");
  if (!elements.screenshotPrompt.value.trim()) {
    elements.screenshotPrompt.value = "Summarize the visible information and point out anything that needs attention.";
  }
  setStatus(`Captured ${capture.name || "screen"}`);
}

async function startScreenshotSummary() {
  requireAuth();
  if (!currentScreenshot) {
    await captureScreen();
  }
  if (!isUsableImageDataUrl(currentScreenshot)) {
    throw new Error("Capture the screen again before summarizing.");
  }
  const prompt = elements.screenshotPrompt.value.trim() || "Summarize this screen.";
  addMessage("user", prompt);
  setBusy(true, `Summarizing with ${tier === "deep" ? "Deep" : "Flash"}`);
  const data = await apiRequest("/desktop/screenshot/summarize", {
    method: "POST",
    json: {
      image_data_url: currentScreenshot,
      prompt,
      reasoning_mode: tier
    }
  });
  setActiveContext({
    type: "screenshot",
    title: activeContext && activeContext.type === "screenshot" ? activeContext.title : "Screen capture",
    detail: "Screenshot summary is in chat. Ask follow-ups from the current context.",
    preview: currentScreenshot,
    suggestions: contextSuggestions({ type: "screenshot" })
  });
  addMessage("assistant", data.summary || "No screenshot summary returned.");
  elements.screenshotPanel.classList.add("hidden");
  setStatus("Ready");
  switchToChat();
}

function handleFiles(files) {
  const file = Array.from(files || [])[0];
  if (!file) {
    return;
  }
  uploadFile(file).catch((error) => {
    setStatus(error.message, "error");
  });
}

function handleDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  elements.dropZone.classList.remove("dragging");
  elements.petView.classList.remove("dragging");
  handleFiles(event.dataTransfer.files);
}

function handleDragOver(event) {
  event.preventDefault();
  event.stopPropagation();
  const target = appMode === "pet" ? elements.petView : elements.dropZone;
  target.classList.add("dragging");
}

function handleDragLeave(event) {
  event.stopPropagation();
  if (event.currentTarget === document.body) {
    elements.dropZone.classList.remove("dragging");
    elements.petView.classList.remove("dragging");
    return;
  }
  if (event.currentTarget === elements.petView || event.currentTarget === elements.dropZone) {
    event.currentTarget.classList.remove("dragging");
  }
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function bindEvents() {
  elements.tierFlashButton.addEventListener("click", () => setTier("flash"));
  elements.tierDeepButton.addEventListener("click", () => setTier("deep"));
  elements.petExpandButton.addEventListener("click", () => setAppMode("work"));
  elements.petModeButton.addEventListener("click", () => setAppMode("pet"));
  elements.switchToChatButton.addEventListener("click", () => switchToChat());
  elements.backToWorkButton.addEventListener("click", () => setAppMode("work"));

  elements.loginButton.addEventListener("click", handleLogin);
  elements.logoutButton.addEventListener("click", handleLogout);
  elements.passwordInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      handleLogin();
    }
  });

  elements.petUploadButton.addEventListener("click", openFilePicker);
  elements.uploadButton.addEventListener("click", openFilePicker);
  elements.fileInput.addEventListener("change", (event) => handleFiles(event.target.files));

  for (const target of [document.body, elements.dropZone, elements.petView]) {
    target.addEventListener("dragover", handleDragOver);
    target.addEventListener("dragleave", handleDragLeave);
    target.addEventListener("drop", handleDrop);
  }

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

  elements.petCaptureButton.addEventListener("click", () => {
    captureScreen().catch((error) => {
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
    startScreenshotSummary().catch((error) => {
      setStatus(error.message, "error");
    }).finally(() => {
      setBusy(false);
    });
  });
  elements.openWebButton.addEventListener("click", () => {
    window.desktopAPI.openExternal(WEB_APP_URL);
  });
  elements.closeButton.addEventListener("click", () => {
    window.desktopAPI.close();
  });
}

function init() {
  renderTier();
  renderAuth();
  renderMessages();
  renderContext();
  renderSuggestions();
  bindEvents();
  setStatus(isSignedIn() ? "Ready" : "Sign in");
  setAppMode(isSignedIn() ? "pet" : "work");
}

init();
