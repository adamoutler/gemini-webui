function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
function filterTerminalFluff(text) {
  if (!text) return "";

  // Replace box-drawing and block characters with spaces
  let filtered = text.replace(/[\u2500-\u259F]/g, " ");

  // Process line by line to remove specific terminal status bars and trailing spaces
  let lines = filtered.split("\n");
  lines = lines
    .filter((line) => {
      // Exclude the bottom status bar and prompt hints
      if (line.includes("workspace (") && line.includes("branch:"))
        return false;
      if (line.includes("Shift+Tab to accept edits")) return false;
      return true;
    })
    .map((line) => line.replace(/[ \t]+$/, "")); // Trim trailing spaces on every line

  return lines.join("\n");
}
window.ENABLE_DEBUG = localStorage.getItem("GEMINI_DEBUG") === "true";
window.setDebug = function (enabled) {
  window.ENABLE_DEBUG = !!enabled;
  if (enabled) {
    localStorage.setItem("GEMINI_DEBUG", "true");
    console.log("Verbose debugging enabled. To disable, run: setDebug(false)");
  } else {
    localStorage.removeItem("GEMINI_DEBUG");
    console.log("Verbose debugging disabled. To enable, run: setDebug(true)");
  }
};
function debugLog(...args) {
  if (window.ENABLE_DEBUG) {
    console.log(...args);
  }
}
let isRefreshingToken = false;
let tokenRefreshSubscribers = [];
let csrfRefreshAttempts = 0;
let lastCsrfRefreshTime = 0;

async function refreshCsrfToken() {
  const now = Date.now();
  if (now - lastCsrfRefreshTime < 500) {
    csrfRefreshAttempts++;
  } else {
    csrfRefreshAttempts = 0;
  }
  lastCsrfRefreshTime = now;

  if (csrfRefreshAttempts > 10) {
    const details = document.getElementById("connection-issue-details");
    if (details) details.innerText = "Error: Too many CSRF refresh attempts.";
    const modal = document.getElementById("connection-issue-modal");
    if (modal) modal.style.display = "block";
    throw new Error("Too many CSRF refresh attempts");
  }

  if (isRefreshingToken) {
    return new Promise((resolve) => tokenRefreshSubscribers.push(resolve));
  }
  isRefreshingToken = true;
  try {
    const response = await originalFetch("/api/csrf-token", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Failed to fetch token");
    const data = await response.json();
    const newToken = data.csrf_token;
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) metaTag.setAttribute("content", newToken);
    tokenRefreshSubscribers.forEach((cb) => cb(newToken));
    return newToken;
  } finally {
    isRefreshingToken = false;
    tokenRefreshSubscribers = [];
  }
}

const originalFetch = window.fetch;
window.fetch = async function () {
  let currentCsrfToken = document
    .querySelector('meta[name="csrf-token"]')
    ?.getAttribute("content");
  let [resource, config] = arguments;
  if (config === undefined) {
    config = {};
  }

  const injectToken = (token, cfg) => {
    if (
      cfg.method &&
      ["POST", "PUT", "DELETE", "PATCH"].includes(cfg.method.toUpperCase())
    ) {
      if (cfg.headers instanceof Headers) {
        if (token) cfg.headers.set("X-CSRFToken", token);
      } else {
        cfg.headers = cfg.headers || {};
        if (token) cfg.headers["X-CSRFToken"] = token;
      }
    }
  };

  injectToken(currentCsrfToken, config);

  let response = await originalFetch(resource, config);

  if (response.status === 400 || response.status === 403) {
    try {
      const clonedResponse = response.clone();
      const data = await clonedResponse.json();
      if (data && data.csrf_expired === true && !config.skipCsrfReload) {
        const newToken = await refreshCsrfToken();
        injectToken(newToken, config);
        response = await originalFetch(resource, config);
      }
    } catch (e) {
      // Ignore JSON parse errors for non-JSON responses
    }
  }
  return response;
};

// PWA Service Worker Registration
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => {
        debugLog("SW registered:", reg);
      })
      .catch((err) => {
        debugLog("SW registration failed:", err);
      });
  });
}

window.addEventListener("beforeinstallprompt", (e) => {
  debugLog("beforeinstallprompt event fired");
  // e.preventDefault(); // Don't prevent default, we want the browser prompt
});

window.addEventListener("appinstalled", (evt) => {
  debugLog("Gemini WebUI was installed");
});

// Request Notification Permission
if ("Notification" in window && Notification.permission === "default") {
  document.addEventListener(
    "click",
    () => {
      if (Notification.permission === "default") {
        Notification.requestPermission();
      }
    },
    { once: true },
  );
}

let tabs = [];
const DEFAULT_PROMPTS = [
  {
    name: "Explain Code",
    text: "Please explain the code in the current context.",
  },
  {
    name: "Refactor Code",
    text: "Suggest improvements and refactor the code in the current context.",
  },
  {
    name: "Summarize File",
    text: "Provide a high-level summary of the file's purpose and functionality.",
  },
  {
    name: "Gemini Audit",
    text: "Please run a security audit on the current context.",
  },
];

let currentEditPromptIndex = -1;
let customPrompts = [];

async function loadPromptsFromServer() {
  try {
    const response = await fetch("/api/prompts");
    if (response.ok) {
      customPrompts = await response.json();
    }
  } catch (e) {
    console.error("Failed to load prompts from server:", e);
    // Fallback to localStorage for backward compatibility or offline
    try {
      customPrompts = JSON.parse(localStorage.getItem("custom_prompts")) || [];
    } catch (err) {
      customPrompts = [];
    }
  }
}

function getCustomPrompts() {
  return customPrompts;
}

function sendPromptToTab(tabId, text) {
  const tab = tabs.find((t) => t.id === tabId);
  if (tab && tab.socket && tab.state === "terminal") {
    // Ensure it ends with a newline to execute
    const input =
      text.endsWith("\n") || text.endsWith("\r") ? text : text + "\r";
    tab.socket.emit("pty-input", { input: input });
  } else {
    alert("Tab is not connected to a terminal.");
  }
}
let activeTabId = null;
let ctrlActive = false;
let altActive = false;
let initialAutoResumeDone = false;
let launcherRefreshInterval = null;
let titleFlashInterval = null;
let originalPageTitle = "Gemini WebUI";

const urlParams = new URLSearchParams(window.location.search);
const mode = urlParams.get("mode");
const sessionId = urlParams.get("session_id");
const deepHost = urlParams.get("host");
const deepTarget = urlParams.get("target");
const deepDir = urlParams.get("dir");

const HostStateManager = {
  states: {},

  updateState: function (label, isSuccess) {
    if (!this.states[label]) this.states[label] = { failures: -1 };

    if (isSuccess) {
      this.states[label].failures = 0;
    } else {
      if (this.states[label].failures < 0) this.states[label].failures = 2;
      else this.states[label].failures++;
    }

    return this.states[label].failures;
  },

  getIndicator: function (failures) {
    if (failures === 0) return "🟢";
    if (failures === 1) return "🟡";
    if (failures < 0) return "⚪";
    return "🔴";
  },

  getStatusClass: function (failures) {
    if (failures === 0) return "connected";
    if (failures === 1) return "degraded";
    if (failures < 0) return "offline";
    return "error";
  },

  renderHealthUI: function (tabId, label, failures) {
    const indicatorId = `${tabId}_health_${label.replace(/[^a-z0-9]/gi, "")}`;
    const el = document.getElementById(indicatorId);
    if (el) {
      el.innerText = this.getIndicator(failures);
      el.dataset.status = this.getStatusClass(failures);
    }
  },

  triggerPulse: function (tabId, label) {
    const pulseId = `${tabId}_pulse_${label.replace(/[^a-z0-9]/gi, "")}`;
    const pulseEl = document.getElementById(pulseId);
    if (pulseEl) {
      pulseEl.classList.remove("pulsing", "superbright");
      void pulseEl.offsetWidth; // trigger reflow
      requestAnimationFrame(() => {
        pulseEl.classList.add("pulsing", "superbright");
      });
    }
  },

  updateHealth: function (tabId, label, isSuccess, shouldPulse = false) {
    const prevClass = this.getInitialStatusClass(label);
    debugLog("UPDATE HEALTH CALLED WITH " + isSuccess);
    const failures = this.updateState(label, isSuccess);
    const newClass = this.getStatusClass(failures);
    this.renderHealthUI(tabId, label, failures);
    if (shouldPulse || prevClass !== newClass) {
      this.triggerPulse(tabId, label);
    }
  },
  getInitialIndicator: function (label) {
    if (!this.states[label]) return "⚪";
    return this.getIndicator(this.states[label].failures);
  },

  getInitialStatusClass: function (label) {
    if (!this.states[label]) return "offline";
    return this.getStatusClass(this.states[label].failures);
  },
};

let wakeLock = null;

async function updateWakeLock() {
  if (!("wakeLock" in navigator)) return;

  const isActive = tabs.some(
    (t) => t.title && (t.title.includes("Working") || t.title.includes("✋")),
  );

  if (isActive && document.visibilityState === "visible") {
    if (!wakeLock) {
      try {
        wakeLock = await navigator.wakeLock.request("screen");
        wakeLock.addEventListener("release", () => {
          wakeLock = null;
        });
      } catch (err) {
        console.error(`Wake Lock error: ${err.name}, ${err.message}`);
      }
    }
  } else {
    if (wakeLock) {
      wakeLock.release().then(() => {
        wakeLock = null;
      });
    }
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    updateWakeLock();
  }
});

function updateHostHealthIndicator(tabId, label, isSuccess) {
  HostStateManager.updateHealth(tabId, label, isSuccess, true);
}

function updatePageTitle() {
  updateWakeLock();
  const hasActionRequired = tabs.some((t) => t.title && t.title.includes("✋"));
  const baseTitle = hasActionRequired ? "✋ Gemini WebUI" : originalPageTitle;

  if (!hasActionRequired) {
    if (titleFlashInterval) {
      clearInterval(titleFlashInterval);
      titleFlashInterval = null;
    }
    document.title = baseTitle;
  } else {
    if (!document.hasFocus()) {
      if (!titleFlashInterval) {
        document.title = baseTitle;
        const tempTitle = "⚠️ Action Required! ✋";
        titleFlashInterval = setInterval(() => {
          document.title = document.title === baseTitle ? tempTitle : baseTitle;
        }, 1000);
      }
    } else {
      if (titleFlashInterval) {
        clearInterval(titleFlashInterval);
        titleFlashInterval = null;
      }
      document.title = baseTitle;
    }
  }
}

window.addEventListener("focus", () => {
  if (titleFlashInterval) {
    clearInterval(titleFlashInterval);
    titleFlashInterval = null;
    const hasActionRequired = tabs.some(
      (t) => t.title && t.title.includes("✋"),
    );
    document.title = hasActionRequired ? "✋ Gemini WebUI" : originalPageTitle;
  }
});

async function loadTabsFromServer() {
  try {
    const response = await fetch("/api/sessions/persisted");
    if (!response.ok) throw new Error("Failed to fetch sessions");
    const persisted = await response.json();

    // Clear existing tabs
    tabs = [];
    document.getElementById("terminal-container").innerHTML = "";

    // Add persisted tabs
    let foundActive = false;
    for (const tid in persisted) {
      const s = persisted[tid];
      const tab = {
        id: tid,
        term: null,
        fitAddon: null,
        socket: null,
        session: s,
        title: s.title,
        state: "terminal",
      };
      tabs.push(tab);
      createTerminalContainer(tid);
      if (tid === activeTabId) foundActive = true;
    }

    // Always add a launcher if none exist
    if (!tabs.find((t) => t.state === "launcher")) {
      const id = "tab_" + (Date.now() + Math.floor(Math.random() * 1000));
      tabs.push({
        id,
        term: null,
        fitAddon: null,
        socket: null,
        session: null,
        title: "New Tab",
        state: "launcher",
      });
      createTerminalContainer(id);
      renderLauncher(id);
    }

    if (!foundActive) activeTabId = tabs[0].id;

    renderTabs();
    switchTab(activeTabId);

    // Start sessions
    tabs.forEach((t) => {
      if (t.state === "terminal") {
        recreateTerminalUI(t, true);
      }
    });

    // Handle migration from legacy pinned tabs
    const legacyPinned = localStorage.getItem("pinned_tabs");
    if (legacyPinned) {
      try {
        const pins = JSON.parse(legacyPinned);
        if (Array.isArray(pins) && pins.length > 0) {
          fetch("/api/migrate-tabs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              tabs: pins.map((p) => ({
                tab_id: p.id,
                title: p.title,
                ssh_target: p.ssh_target,
                ssh_dir: p.ssh_dir,
              })),
            }),
          }).then(() => localStorage.removeItem("pinned_tabs"));
        } else {
          localStorage.removeItem("pinned_tabs");
        }
      } catch (e) {
        localStorage.removeItem("pinned_tabs");
      }
    }
  } catch (e) {
    debugLog("Error loading tabs from server:", e);
    if (tabs.length === 0) addNewTab();
  }
}

function syncTabs(serverTabs) {
  debugLog("Syncing tabs from server:", serverTabs);
  let changed = false;

  // Remove tabs no longer on server
  for (let i = tabs.length - 1; i >= 0; i--) {
    const t = tabs[i];
    if (t.state === "terminal" && !serverTabs[t.id]) {
      closeTab(t.id, null, true);
      changed = true;
    }
  }

  // Add or update tabs
  for (const tid in serverTabs) {
    const s = serverTabs[tid];
    const existing = tabs.find((t) => t.id === tid);
    if (!existing) {
      const tab = {
        id: tid,
        term: null,
        fitAddon: null,
        socket: null,
        session: s,
        title: s.title,
        state: "terminal",
      };
      tabs.push(tab);
      createTerminalContainer(tid);
      recreateTerminalUI(tab, true);
      changed = true;
    } else if (existing.title !== s.title) {
      existing.title = s.title;
      changed = true;
    }
  }

  if (changed) {
    renderTabs();
    updatePageTitle();
  }
}

function createTerminalContainer(id) {
  if (document.getElementById(id + "_instance")) return;
  const container = document.createElement("div");
  container.id = id + "_instance";
  container.className = "tab-instance";
  document.getElementById("terminal-container").appendChild(container);
}

function saveTabsToStorage() {
  sessionStorage.setItem("gemini_active_tab", activeTabId);
}

function loadTabsFromStorage() {
  loadTabsFromServer();
  return true;
}

function recreateTerminalUI(tab, shouldReclaim = false) {
  const container = document.getElementById(tab.id + "_instance");
  container.innerHTML = "";
  const termDiv = document.createElement("div");
  termDiv.className = "terminal-instance";
  termDiv.id = "rolling-log-" + tab.id;
  container.appendChild(termDiv);
  startSession(
    tab.id,
    tab.session.type,
    tab.session.ssh_target,
    tab.session.ssh_dir,
    tab.session.resume,
    tab.title,
    shouldReclaim,
  );
}

const checkMobile = () => {
  // Strictly target Android as requested
  const isAndroid = /Android/i.test(navigator.userAgent);
  const isTouch = "ontouchstart" in window || navigator.maxTouchPoints > 0;

  // Increase width threshold to 1024px to support Android tablets (Nexus 9/Pixel Tablet)
  const isNarrow = window.innerWidth <= 1024;

  // Explicitly exclude Apple devices
  const isApple = /iPhone|iPad|iPod|Macintosh/i.test(navigator.userAgent);

  // Return true if explicitly Android, or a narrow touch device that is not Apple
  return isAndroid || (isNarrow && isTouch && !isApple);
};
const isMobile = checkMobile();
if (isMobile) {
  document.documentElement.classList.add("is-mobile");
}
debugLog(
  "Environment detection: isMobile =",
  isMobile,
  "(UA:",
  navigator.userAgent,
  "Width:",
  window.innerWidth,
  "Touch:",
  "ontouchstart" in window || navigator.maxTouchPoints > 0,
  ")",
);

// VisualViewport logic is handled at the bottom of the script

window.addEventListener("popstate", (event) => {
  const activeTab = tabs.find((t) => t.id === activeTabId);
  // Only hijack if we are currently in a terminal.
  // If we are already in launcher mode, let the back button work normally.
  if (activeTab && activeTab.state === "terminal") {
    addNewTab();
  }
});

let savedTheme = localStorage.getItem("gemini_theme");
let customTheme = savedTheme ? JSON.parse(savedTheme) : {};
const defaultFontSize = isMobile ? 10 : 14;
let customFontSize = localStorage.getItem("gemini_font_size");
let currentFontSize = customFontSize
  ? parseInt(customFontSize)
  : defaultFontSize;

const terminalTheme = {
  background: customTheme.background || "#1e1e1e",
  foreground: customTheme.foreground || "#d4d4d4",
  cursor: customTheme.cursor || "#ffffff",
  selection: "#264f78",
  black: "#000000",
  red: "#cd3131",
  green: "#0dbc79",
  yellow: "#e5e510",
  blue: "#2472c8",
  magenta: "#bc3fbc",
  cyan: "#11a8cd",
  white: "#e5e5e5",
  brightBlack: "#666666",
  brightRed: "#f14c4c",
  brightGreen: "#23d18b",
  brightYellow: "#f5f543",
  brightBlue: "#3b8eea",
  brightMagenta: "#d670d6",
  brightCyan: "#29b8db",
  brightWhite: "#e5e5e5",
};

// Initialize CSS variables immediately to reflect any saved theme
document.documentElement.style.setProperty(
  "--terminal-bg",
  terminalTheme.background,
);
document.documentElement.style.setProperty(
  "--terminal-fg",
  terminalTheme.foreground,
);

function initThemeUI() {
  document.documentElement.style.setProperty(
    "--terminal-bg",
    terminalTheme.background,
  );
  document.documentElement.style.setProperty(
    "--terminal-fg",
    terminalTheme.foreground,
  );
  document.getElementById("theme-bg").value = terminalTheme.background;
  document.getElementById("theme-fg").value = terminalTheme.foreground;
  document.getElementById("theme-cursor").value = terminalTheme.cursor;
  document.getElementById("theme-font").value = currentFontSize;
}

function applyTheme() {
  terminalTheme.background = document.getElementById("theme-bg").value;
  terminalTheme.foreground = document.getElementById("theme-fg").value;
  terminalTheme.cursor = document.getElementById("theme-cursor").value;
  currentFontSize =
    parseInt(document.getElementById("theme-font").value) || defaultFontSize;

  localStorage.setItem(
    "gemini_theme",
    JSON.stringify({
      background: terminalTheme.background,
      foreground: terminalTheme.foreground,
      cursor: terminalTheme.cursor,
    }),
  );
  localStorage.setItem("gemini_font_size", currentFontSize);

  // Set CSS variables for global styling matching the theme
  document.documentElement.style.setProperty(
    "--terminal-bg",
    terminalTheme.background,
  );
  document.documentElement.style.setProperty(
    "--terminal-fg",
    terminalTheme.foreground,
  );

  // Apply to all open terminals
  tabs.forEach((tab) => {
    if (tab.term) {
      tab.term.options.theme = terminalTheme;
      tab.term.options.fontSize = currentFontSize;
      if (tab.term.textarea) {
      }
      fitTerminal(tab);
    }
  });
}

function resetTheme() {
  localStorage.removeItem("gemini_theme");
  localStorage.removeItem("gemini_font_size");
  terminalTheme.background = "#1e1e1e";
  terminalTheme.foreground = "#d4d4d4";
  terminalTheme.cursor = "#ffffff";
  currentFontSize = defaultFontSize;
  initThemeUI();

  // Apply immediately to terminals
  tabs.forEach((tab) => {
    if (tab.term) {
      tab.term.options.theme = terminalTheme;
      tab.term.options.fontSize = currentFontSize;
      fitTerminal(tab);
    }
  });
}

function updateStatus(target, dir) {
  const statusEl = document.getElementById("connection-status");
  if (target === "local" || target === "picker" || !target) {
    statusEl.innerText = target === "picker" ? "launcher" : "local";
    statusEl.style.color = "#2472c8";
  } else {
    const host = target.split("@").pop();
    statusEl.innerText = "ssh: " + host + (dir ? ":" + dir : "");
    statusEl.style.color = "#0dbc79";
  }
}

async function addNewTab(autoResume = false) {
  // If a launcher tab already exists, just switch to it instead of creating a new one.
  const existingLauncher = tabs.find((t) => t.state === "launcher");
  if (existingLauncher) {
    switchTab(existingLauncher.id);
    return;
  }

  const id = "tab_" + (Date.now() + Math.floor(Math.random() * 1000));
  const tab = {
    id,
    term: null,
    fitAddon: null,
    socket: null,
    session: null,
    title: "New Tab",
    state: "launcher",
  };
  const container = document.createElement("div");
  container.id = id + "_instance";
  container.className = "tab-instance";
  document.getElementById("terminal-container").appendChild(container);
  tabs.push(tab);
  renderTabs();
  switchTab(id);
  renderLauncher(id);
  saveTabsToStorage();
}

let backendSessionLastSeen = {};
let backendSessionStatusClass = {};

function refreshBackendSessionsList(id) {
  const listEl = document.getElementById(`${id}_backend_sessions`);
  if (!listEl) return; // Tab closed or switched

  const socket = getGlobalSocket();
  socket.emit("get_management_sessions", (sessions) => {
    const terminateAllBtn = document.getElementById(`${id}_terminate_all_btn`);
    if (terminateAllBtn) {
      terminateAllBtn.style.display =
        sessions && sessions.length > 0 ? "block" : "none";
    }

    if (!sessions || sessions.length === 0) {
      listEl.innerHTML =
        '<div class="js-style-536955">No detached sessions found on the server.</div>';
      return;
    }

    const seenSessionIds = new Set();
    if (
      listEl.innerHTML.includes("No detached sessions found on the server.")
    ) {
      listEl.innerHTML = "";
    }

    sessions.forEach((s) => {
      seenSessionIds.add(s.tab_id);
      const statusClass = s.is_orphaned ? "status-orphaned" : "status-online";
      const statusLabel = s.is_orphaned ? "Orphaned" : "Active";

      let shouldFlash = backendSessionLastSeen[s.tab_id] !== s.last_active;

      backendSessionLastSeen[s.tab_id] = s.last_active;
      backendSessionStatusClass[s.tab_id] = statusClass;

      const shortDir = s.ssh_dir ? s.ssh_dir.split("/").pop() : "";
      const dirContext = shortDir
        ? `<span class="js-style-b629a7">[${escapeHtml(shortDir)}]</span>`
        : "";
      const lastSeenDate = s.last_active
        ? new Date(s.last_active * 1000).toLocaleString()
        : "Unknown";

      const existingNode = document.getElementById(
        `managed-session-${id}-${s.tab_id}`,
      );

      if (existingNode) {
        const statusNode = existingNode.querySelector(".status-node");
        if (statusNode) {
          statusNode.className = `status-node ${statusClass}`;
          if (shouldFlash) {
            statusNode.classList.remove("flash");
            void statusNode.offsetWidth; // trigger reflow
            statusNode.classList.add("flash");
          }
        }
        const statusLabelNode = existingNode.querySelector(".status-label");
        if (statusLabelNode) {
          statusLabelNode.innerText = statusLabel;
        }
        const lastSeenNode = existingNode.querySelector(
          ".session-last-seen-display",
        );
        if (lastSeenNode) {
          lastSeenNode.innerText = `Last seen: ${lastSeenDate}`;
        }
      } else {
        const newNode = document.createElement("div");
        newNode.id = `managed-session-${id}-${s.tab_id}`;
        newNode.className = "session-item";
        newNode.style.cssText =
          "background: #252526; margin-bottom: 8px; padding: 12px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #333;";

        let flashClass = shouldFlash ? " flash" : "";
        newNode.innerHTML = `
                            <div class="session-info">
                                <div class="js-style-990843">${dirContext}${s.title}</div>
                                <div class="js-style-2ef6c5">
                                    <span class="js-style-133a0c">
                                        <span class="status-node ${statusClass}${flashClass}"></span>
                                        <span class="status-label">${statusLabel}</span>
                                    </span>
                                    <span class="js-style-5fd781">|</span>
                                    <span>ID: ${s.tab_id}</span>
                                    <span class="js-style-5fd781">|</span>
                                    <span class="session-last-seen-display">Last seen: ${lastSeenDate}</span>
                                </div>
                            </div>
                            `;
        listEl.appendChild(newNode);
      }
    });

    Array.from(listEl.children).forEach((child) => {
      if (child.id && child.id.startsWith(`managed-session-${id}-`)) {
        const tabId = child.id.replace(`managed-session-${id}-`, "");
        if (!seenSessionIds.has(tabId)) {
          listEl.removeChild(child);
        }
      }
    });
  });
}

async function renderLauncher(id) {
  const config = await (await fetch("/api/config")).json();
  const container = document.getElementById(id + "_instance");

  let warningHtml = "";
  if (!config.DATA_WRITABLE && !config.TMP_WRITABLE) {
    warningHtml = `
                    <div class="js-style-31256e">
                        <strong>CRITICAL: No writable storage found.</strong><br>
                        Both /data and /tmp are read-only. Settings and keys cannot be saved.
                        Local sessions will not persist. Please mount a volume or enable tmpfs.
                    </div>`;
  } else if (!config.DATA_WRITABLE) {
    warningHtml = `
                    <div class="js-style-f80c50">
                        <strong>WARNING:</strong> Persistent storage (/data) is not writable.
                        Using temporary storage. Settings will be lost on restart.
                    </div>`;
  }

  container.innerHTML = `
                <div class="launcher">
                    <h2>Select a Connection</h2>
                    <div class="js-style-a1ebd3">
                        <strong>Note:</strong> Sessions are isolated by project directory and user.
                        If you don't see your sessions, ensure the path below matches your host project.
                    </div>
                    ${warningHtml}
                    <!-- Quick Connect Bar -->
                    <div class="quick-connect-bar">
                        <span class="quick-connect-label">ssh</span>
                        <input type="text" id="${id}_quick_input" class="quick-connect-input" placeholder="user@host:port ~/folder" onkeydown="if(event.key === 'Enter') quickConnectAction('${id}', 'connect')">
                        <button class="primary" data-onclick="quickConnectAction('${id}', 'key')">Add Key</button>
                        <button class="success" data-onclick="quickConnectAction('${id}', 'connect')">Connect</button>
                    </div>

                    <div id="${id}_connections" class="connections-list"></div>


                    </div>
                </div>`;

  // Initial fetch
  refreshBackendSessionsList(id);

  const hosts = await (await fetch("/api/hosts")).json();

  // Set up polling while this launcher is visible
  const connContainer = document.getElementById(id + "_connections");
  let draggedCard = null;
  let placeholder = document.createElement("div");
  placeholder.className = "drag-placeholder";

  hosts.forEach((conn, index) => {
    const card = document.createElement("div");
    card.className = "connection-card";
    card.dataset.label = conn.label;

    const sessionListId = `${id}_sessions_${conn.label.replace(
      /[^a-z0-9]/gi,
      "",
    )}`;
    const healthId = `${id}_health_${conn.label.replace(/[^a-z0-9]/gi, "")}`;
    const pulseId = `${id}_pulse_${conn.label.replace(/[^a-z0-9]/gi, "")}`;

    let initialIndicator = HostStateManager.getInitialIndicator(conn.label);
    let initialStatus = HostStateManager.getInitialStatusClass(conn.label);

    card.innerHTML = `
                    <div class="connection-header">
                        <div class="connection-drag-handle" title="Drag to reorder" draggable="true">⠿</div>
                        <div class="connection-title">
                            <div class="js-style-86447b">
                                <div class="js-style-27eef0">
                                    <span id="${healthId}" data-status="${initialStatus}" class="js-style-ae2742">${initialIndicator}</span>
                                    <div id="${pulseId}" class="pulse-indicator"></div>
                                </div>
                                <span>${conn.label}</span>
                            </div>
                            <div class="js-style-cf9e3e">${
                              conn.target || "local"
                            } ${conn.dir || ""}</div>
                        </div>
                        <div class="connection-actions">
                            <button class="secondary" data-onclick="startSession('${id}', '${
                              conn.type
                            }', '${conn.target || ""}', '${
                              conn.dir || ""
                            }', true)">Resume Last</button>
                            <button class="primary" data-onclick="startSession('${id}', '${
                              conn.type
                            }', '${conn.target || ""}', '${
                              conn.dir || ""
                            }', 'new')">Start New</button>

                        </div>
                    </div>
                    <div id="${sessionListId}" class="session-list-container"><div class="js-style-2a672e">Loading sessions...</div></div>`;

    const handle = card.querySelector(".connection-drag-handle");

    handle.addEventListener("contextmenu", (e) => e.preventDefault());

    handle.addEventListener("dragstart", (e) => {
      draggedCard = card;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", conn.label);

      // Set the drag image to the whole card instead of just the handle
      const rect = card.getBoundingClientRect();
      if (e.dataTransfer.setDragImage) {
        e.dataTransfer.setDragImage(
          card,
          e.clientX - rect.left,
          e.clientY - rect.top,
        );
      }

      // Use setTimeout to ensure the "dragging" class is added after the drag image is generated
      setTimeout(() => {
        card.classList.add("dragging");
        card.after(placeholder);
        placeholder.style.height = card.offsetHeight + "px";
      }, 0);
    });

    handle.addEventListener("dragend", () => {
      if (!draggedCard) return;
      draggedCard.classList.remove("dragging");
      if (placeholder.parentNode) {
        placeholder.replaceWith(draggedCard);
      }
      draggedCard = null;

      // Final background update
      const newLabels = Array.from(
        connContainer.querySelectorAll(".connection-card"),
      ).map((c) => c.dataset.label);
      fetch("/api/hosts/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newLabels),
      });
    });

    let dragOffset = { x: 0, y: 0 };

    // Touch support for mobile dragging
    handle.addEventListener(
      "touchstart",
      (e) => {
        draggedCard = card;
        const rect = card.getBoundingClientRect();
        const touch = e.touches[0];
        dragOffset.x = touch.clientX - rect.left;
        dragOffset.y = touch.clientY - rect.top;

        card.style.width = rect.width + "px";
        card.classList.add("dragging-mobile");
        card.style.position = "fixed";
        card.style.left = touch.clientX - dragOffset.x + "px";
        card.style.top = touch.clientY - dragOffset.y + "px";
      },
      { passive: false },
    );

    handle.addEventListener(
      "touchmove",
      (e) => {
        e.preventDefault();
        if (!draggedCard) return;
        const touch = e.touches[0];

        draggedCard.style.left = touch.clientX - dragOffset.x + "px";
        draggedCard.style.top = touch.clientY - dragOffset.y + "px";

        const target = document.elementFromPoint(touch.clientX, touch.clientY);
        const overCard = target ? target.closest(".connection-card") : null;

        if (
          overCard &&
          overCard !== draggedCard &&
          !overCard.classList.contains("dragging-mobile")
        ) {
          const rect = overCard.getBoundingClientRect();
          const midpoint = rect.top + rect.height / 2;
          if (touch.clientY < midpoint) {
            overCard.before(draggedCard);
          } else {
            overCard.after(draggedCard);
          }
        }
      },
      { passive: false },
    );

    handle.addEventListener("touchend", (e) => {
      if (!draggedCard) return;
      draggedCard.classList.remove("dragging-mobile");
      draggedCard.style.position = "";
      draggedCard.style.left = "";
      draggedCard.style.top = "";
      draggedCard.style.width = "";
      draggedCard = null;

      const newLabels = Array.from(
        connContainer.querySelectorAll(".connection-card"),
      ).map((c) => c.dataset.label);
      fetch("/api/hosts/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newLabels),
      });
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      if (!draggedCard || draggedCard === card) return;

      const rect = card.getBoundingClientRect();
      const midpoint = rect.top + rect.height / 2;
      if (e.clientY < midpoint) {
        card.before(placeholder);
      } else {
        card.after(placeholder);
      }
    });

    connContainer.appendChild(card);
    setTimeout(() => {
      fetchSessions(id, conn, sessionListId, false, true); // Use cache first
    }, index * 500);
  });
}

async function terminateBackendSession(launcherTabId, tabId) {
  if (
    !confirm(
      `Are you sure you want to terminate this backend session? Any unsaved work in the terminal will be lost.`,
    )
  )
    return;
  try {
    const response = await fetch(`/api/management/sessions/${tabId}`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
    });
    if (response.ok || response.status === 404) {
      const row = document.getElementById(
        `managed-session-${launcherTabId}-${tabId}`,
      );
      if (row) row.remove();
      // Optional: refresh from backend to ensure consistent state
      refreshBackendSessionsList(launcherTabId);
    } else {
      let errorMessage = "Unknown error";
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.indexOf("application/json") !== -1) {
        try {
          const data = await response.json();
          errorMessage = data.error || data.message || errorMessage;
        } catch (e) {
          errorMessage = "Failed to parse error response.";
        }
      } else {
        errorMessage = await response.text();
      }
      if (response.status === 400 || response.status === 403) {
        errorMessage += " (Auth/CSRF error - please reload the page)";
      }
      alert("Termination failed: " + errorMessage);
    }
  } catch (e) {
    console.error(e);
    alert("Termination failed: " + e.message);
  }
}

async function terminateAllBackendSessions(launcherTabId) {
  if (
    !confirm(
      `Are you sure you want to terminate ALL backend sessions? Any unsaved work in these terminals will be lost.`,
    )
  )
    return;
  try {
    const response = await fetch(`/api/sessions/terminate_all`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
    });
    if (response.ok) {
      refreshBackendSessionsList(launcherTabId);
    } else {
      let errorMessage = "Unknown error";
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.indexOf("application/json") !== -1) {
        try {
          const data = await response.json();
          errorMessage = data.error || data.message || errorMessage;
        } catch (e) {
          errorMessage = "Failed to parse error response.";
        }
      } else {
        errorMessage = await response.text();
      }
      alert("Termination failed: " + errorMessage);
    }
  } catch (e) {
    console.error(e);
    alert("Termination failed: " + e.message);
  }
}

function reclaimBackendSession(id, tabId, title, session) {
  const tab = tabs.find((t) => t.id === id);
  if (!tab) return;

  // Update DOM ID to match new tab ID
  const container = document.getElementById(id + "_instance");
  if (container) container.id = tabId + "_instance";

  if (activeTabId === id) activeTabId = tabId;
  tab.id = tabId; // Switch tab ID to the backend's ID
  tab.title = title;
  tab.state = "terminal";
  tab.session = {
    type: session.ssh_target ? "ssh" : "local",
    ssh_target: session.ssh_target,
    ssh_dir: session.ssh_dir,
    resume: session.resume,
  };

  // Re-render tabs since we changed an ID
  renderTabs();
  saveTabsToStorage();
  recreateTerminalUI(tab, true);
}

let globalSocket = null;
function getGlobalSocket() {
  if (!globalSocket) {
    globalSocket = io.connect(window.location.origin, {
      auth: {
        csrf_token: document
          .querySelector('meta[name="csrf-token"]')
          ?.getAttribute("content"),
      },
      transports: ["websocket", "polling"],
      reconnection: true,
    });
    globalSocket.on("connect_error", async (error) => {
      if (error.message === "invalid_csrf") {
        console.debug("Global socket CSRF token expired. Refreshing token...");
        const newToken = await refreshCsrfToken();
        globalSocket.auth = { csrf_token: newToken };
        globalSocket.connect();
      }
    });

    globalSocket.on("disconnect", () => {
      debugLog("Global socket disconnected");
      if (activeTabId && HostStateManager && HostStateManager.states) {
        Object.keys(HostStateManager.states).forEach((label) => {
          HostStateManager.states[label].failures = 1; // 1 will be incremented to 2 (Red) in updateState
          HostStateManager.updateHealth(activeTabId, label, false, false);
        });
      }
    });

    globalSocket.on("sync-tabs", (serverTabs) => {
      syncTabs(serverTabs);
    });

    globalSocket.on("session-terminated", (data) => {
      debugLog("Session terminated via global socket:", data.tab_id);
      closeTab(data.tab_id, null, true);
    });

    globalSocket.on("sessions_updated", (payload) => {
      if (payload && payload.data && payload.data.output) {
        const sessions = [];
        const regex =
          /^\s*(\d+)\.\s+(.+?)\s+\(([^)]+)\)(?:\s+\[(.*?)\])?\s*$/gm;
        let matchArr;
        while ((matchArr = regex.exec(payload.data.output)) !== null) {
          sessions.push({
            id: matchArr[1],
            name: matchArr[2],
            meta: matchArr[3],
            uuid: matchArr[4],
          });
        }

        tabs.forEach((t) => {
          if (
            t.state === "terminal" &&
            t.session &&
            (t.session.resume === "new" || /^\\d+$/.test(t.session.resume))
          ) {
            const match = sessions.find(
              (s) => s.uuid === t.id || s.id === t.session.resume,
            );
            if (match && match.id) {
              t.session.resume = match.id.toString();
              saveTabsToStorage();
              localStorage.setItem("geminiResume", match.id.toString());
            }
          }
        });
      }

      const activeTab = tabs.find((t) => t.id === activeTabId);
      if (activeTab && activeTab.state === "launcher") {
        const id = activeTab.id;
        const refreshBtn = document.getElementById(`${id}_backend_sessions`);
        if (refreshBtn && payload && payload.host) {
          const conn = payload.host;
          const sessionListId = `${id}_sessions_${conn.label.replace(
            /[^a-z0-9]/gi,
            "",
          )}`;
          fetchSessions(id, conn, sessionListId, false, true, true);
          refreshBackendSessionsList(id);
        }
      }
    });
  }
  return globalSocket;
}

let consecutiveTimeouts = {};

async function fetchSessions(
  tabId,
  conn,
  targetId,
  forceAll = false,
  useCache = false,
  isPolling = false,
) {
  debugLog(
    "FETCH SESSIONS CALLED WITH useCache=" +
      useCache +
      " isPolling=" +
      isPolling,
  );
  if (!window.expandedSessionLists) window.expandedSessionLists = new Set();
  if (window.expandedSessionLists.has(conn.label)) {
    forceAll = true;
  }

  const params = {};
  if (conn.type === "ssh") {
    params.ssh_target = conn.target;
    if (conn.dir) params.ssh_dir = conn.dir;
  }
  if (useCache) params.cache = true;
  params.bg = true;

  try {
    debugLog("FETCH SESSIONS START");
    const data = await new Promise((resolve, reject) => {
      const socket = getGlobalSocket();

      const timeoutTimer = setTimeout(() => {
        resolve({ error: "Timeout waiting for get_sessions" });
      }, 5000);

      socket.emit("get_sessions", params, (response) => {
        clearTimeout(timeoutTimer);
        if (
          response &&
          response.error &&
          !response.output &&
          !response.sessions
        ) {
          resolve(response); // Handle errors explicitly like API did
        } else if (response) {
          resolve(response);
        } else {
          reject(new Error("No response from WebSocket"));
        }
      });
    });

    debugLog("FETCH SESSIONS DATA: ", JSON.stringify(data));
    if (data.status === "fetching") {
      const listEl = document.getElementById(targetId);
      if (listEl && listEl.innerHTML === "") {
        listEl.innerHTML = `<div class="js-style-2a672e">Fetching sessions...</div>`;
      }
      setTimeout(
        () => fetchSessions(tabId, conn, targetId, forceAll, true, true),
        1000,
      );
      return;
    }

    if (!useCache || isPolling) {
      debugLog("ENTERED IF BLOCK");
      try {
        HostStateManager.updateHealth(tabId, conn.label, !data.error, true);
      } catch (e) {
        debugLog("INNER ERROR: " + e.stack);
      }
    }

    const listEl = document.getElementById(targetId);
    if (!listEl) return;

    const timeoutKey = `${tabId}_${conn.label}`;
    if (data.error === "Timeout waiting for get_sessions") {
      consecutiveTimeouts[timeoutKey] =
        (consecutiveTimeouts[timeoutKey] || 0) + 1;

      if (consecutiveTimeouts[timeoutKey] > 5) {
        listEl.innerHTML = `<div class="js-style-7b7303">Connection unstable. Check server logs or try reloading.</div>`;
        return;
      }

      if (!useCache || isPolling) {
        try {
          HostStateManager.updateHealth(tabId, conn.label, false, true);
        } catch (e) {
          debugLog("INNER ERROR: " + e.stack);
        }
      }
      if (
        listEl.innerHTML === "" ||
        listEl.innerHTML.includes("Connecting to server") ||
        listEl.innerHTML.includes("Fetching sessions")
      ) {
        listEl.innerHTML = `<div class="js-style-2a672e">Connecting to server...</div>`;
      }
      setTimeout(
        () => fetchSessions(tabId, conn, targetId, forceAll, useCache, true),
        2000,
      );
      return;
    }

    consecutiveTimeouts[timeoutKey] = 0;

    if (data.error) {
      let errorHtml = `<div class="js-style-7b7303">Error: ${data.error}</div>`;
      if (
        data.error.toLowerCase().includes("permission denied") ||
        data.error.toLowerCase().includes("publickey")
      ) {
        errorHtml += `<div class="js-style-67c8fc"><button class="small primary" data-onclick="openSettings()">Setup Keys</button></div>`;
      }
      listEl.innerHTML = errorHtml;
      if (useCache && !isPolling)
        fetchSessions(tabId, conn, targetId, forceAll, false); // Update after cache load
      return;
    }
    const sessions = parseSessions(data.output || "");

    // UUID Reconciliation
    const activeTerminalTab = tabs.find(
      (t) =>
        t.state === "terminal" &&
        t.session &&
        t.session.ssh_target === conn.target &&
        t.session.ssh_dir === conn.dir,
    );
    if (
      activeTerminalTab &&
      activeTerminalTab.session.resume &&
      (activeTerminalTab.session.resume === "new" ||
        /^\\d+$/.test(activeTerminalTab.session.resume))
    ) {
      const match = sessions.find(
        (s) =>
          s.id === activeTerminalTab.session.resume ||
          s.uuid === activeTerminalTab.id,
      );
      if (match && match.uuid) {
        activeTerminalTab.session.resume = match.uuid;
        saveTabsToStorage();
        localStorage.setItem("geminiResume", match.uuid);
        debugLog("Reconciled ID/new to UUID: " + match.uuid);
      }
    }

    if (sessions.length === 0) {
      listEl.innerHTML = `<div class="js-style-e07506">No active sessions found.</div>`;
    } else {
      const sorted = sessions.reverse();
      const displayCount = forceAll ? sorted.length : 3;
      let html = '<div class="session-list">';
      sorted.slice(0, displayCount).forEach((s) => {
        const shortDir = conn.dir ? conn.dir.split("/").pop() : "";
        const dirContext = shortDir
          ? `<span class="js-style-b629a7">[${escapeHtml(shortDir)}]</span>`
          : "";
        html += `<div class="session-item" data-onclick="startSession('${tabId}', '${
          conn.type
        }', '${conn.target || ""}', '${conn.dir || ""}', '${
          s.uuid
        }', '${escapeHtml(s.name).replace(/'/g, "\\'")}', false)">
                    <div class="session-name">${escapeHtml(s.name)}</div>
                    <div class="session-meta">ID #${s.id} • ${s.meta}</div>
                 </div>`;
      });
      if (!forceAll && sorted.length > 3) {
        html += `<div class="session-item js-style-86c2b8" data-onclick="window.expandedSessionLists.add('${escapeHtml(
          conn.label,
        ).replace(
          /&#039;/g,
          "\\'",
        )}'); fetchSessions('${tabId}', ${JSON.stringify(conn).replace(
          /"/g,
          "&quot;",
        )}, '${targetId}', true, true, true)">... Show ${
          sorted.length - 3
        } more</div>`;
      } else if (forceAll && sorted.length > 3) {
        html += `<div class="session-item js-style-86c2b8" data-onclick="window.expandedSessionLists.delete('${escapeHtml(
          conn.label,
        ).replace(
          /&#039;/g,
          "\\'",
        )}'); fetchSessions('${tabId}', ${JSON.stringify(conn).replace(
          /"/g,
          "&quot;",
        )}, '${targetId}', false, true, true)">... Show less</div>`;
      }
      listEl.innerHTML = html + "</div>";
    }
    if (useCache && !isPolling)
      fetchSessions(tabId, conn, targetId, forceAll, false); // Update after cache load
  } catch (e) {
    if (!useCache || isPolling) {
      debugLog("ENTERED IF BLOCK");
      HostStateManager.updateHealth(tabId, conn.label, false, true);
    }
    console.error(e);
  }
}
function parseSessions(output) {
  const sessions = [];
  const lines = output.split("\n");
  lines.forEach((line) => {
    const match = line.match(/^\s+(\d+)\.\s+(.*)\s+\((.*)\)\s+\[(.*)\]/);
    if (match)
      sessions.push({
        id: match[1],
        name: match[2].trim(),
        meta: match[3],
        uuid: match[4],
      });
  });
  return sessions;
}

function startSession(
  tabId,
  type,
  target,
  dir,
  resumeParam = true,
  sessionName = null,
  shouldReclaim = false,
) {
  const tab = tabs.find((t) => t.id === tabId);
  if (!tab) {
    return;
  }
  tab.state = "terminal";
  tab.session = { type, ssh_target: target, ssh_dir: dir, resume: resumeParam };
  if (!tab.title || tab.title === "New Tab" || tab.title.trim() === "") {
    tab.title = sessionName || (target ? target.split("@").pop() : "Local");
  }
  tab.shouldReclaim = shouldReclaim;

  // Back button hijacking: push state so "back" has something to pop
  window.history.pushState({ terminal: true, tabId: tabId }, "");
  saveTabsToStorage();
  renderTabs();

  const container = document.getElementById(tabId + "_instance");
  container.innerHTML = "";

  const termDiv = document.createElement("div");
  termDiv.className = "terminal-instance";
  termDiv.id = "rolling-log-" + tabId;
  termDiv.setAttribute("role", "log");
  termDiv.setAttribute("aria-live", "polite");
  termDiv.setAttribute("aria-relevant", "additions");
  container.appendChild(termDiv);

  switchTab(tabId);

  if (!isMobile) {
    termDiv.addEventListener(
      "contextmenu",
      (e) => {
        e.preventDefault();
        if (typeof initDesktopContextMenu === "function") {
          initDesktopContextMenu();
        }
        const desktopContextMenu = document.getElementById(
          "desktop-context-menu",
        );
        if (desktopContextMenu) {
          if (tab.term && tab.term.hasSelection()) {
            desktopContextMenu.querySelector("#ctx-copy").style.display =
              "block";
          } else {
            desktopContextMenu.querySelector("#ctx-copy").style.display =
              "none";
          }

          desktopContextMenu.style.display = "block";

          let x = e.pageX;
          let y = e.pageY;

          // Render off-screen initially or just set and fix
          desktopContextMenu.style.left = x + "px";
          desktopContextMenu.style.top = y + "px";

          // Adjust if it goes off screen
          const rect = desktopContextMenu.getBoundingClientRect();
          if (x + rect.width > window.innerWidth) {
            desktopContextMenu.style.left =
              window.innerWidth - rect.width - 5 + "px";
          }
          if (y + rect.height > window.innerHeight) {
            desktopContextMenu.style.top =
              window.innerHeight - rect.height - 5 + "px";
          }
        }
      },
      true,
    );
  }

  tab.term = new Terminal({
    cursorBlink: true,
    cursorStyle: "block",
    macOptionIsMeta: true,
    scrollback: 10000,
    fontSize: currentFontSize,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    allowProposedApi: true,
    theme: terminalTheme,
    scrollOnUserInput: true,
    scrollOnData: false,
  });
  tab.fitAddon = new FitAddon.FitAddon();
  tab.term.loadAddon(tab.fitAddon);

  // WebLinksAddon is disabled in favor of the custom LinkProvider for wrapped lines
  // if (typeof WebLinksAddon !== "undefined") {
  //   tab.term.loadAddon(new WebLinksAddon.WebLinksAddon());
  // }

  tab.term.open(termDiv);

  tab.term.element.addEventListener("copy", (e) => {
    const selection = tab.term.getSelection();
    if (selection) {
      e.clipboardData.setData("text/plain", filterTerminalFluff(selection));
      e.preventDefault();
    }
  });

  try {
    const webglDisabled =
      urlParams.get("webgl") === "false" || navigator.webdriver;
    if (typeof WebglAddon !== "undefined" && !webglDisabled) {
      tab.webglAddon = new WebglAddon.WebglAddon();
      tab.term.loadAddon(tab.webglAddon);
      tab.webglAddon.onContextLoss(() => {
        console.warn("WebGL Context lost, disposing addon");
        tab.webglAddon.dispose();
      });
    } else if (typeof WebglAddon !== "undefined") {
      debugLog("WebGL addon explicitly disabled or test environment detected");
    }
  } catch (e) {
    debugLog("WebGL addon could not be loaded", e);
  }

  // Passive Portal Implementation for Native Momentum
  if (isMobile) {
    const proxy = document.createElement("div");
    proxy.className = "mobile-scroll-proxy";
    const content = document.createElement("div");
    content.className = "mobile-scroll-content";

    const selectionOverlay = document.createElement("div");
    selectionOverlay.className = "mobile-selection-overlay";
    selectionOverlay.style.position = "absolute";
    selectionOverlay.style.left = "0";
    selectionOverlay.style.width = "100%";
    selectionOverlay.style.height = "100%";
    selectionOverlay.style.boxSizing = "border-box";
    selectionOverlay.style.color = "transparent";
    selectionOverlay.style.userSelect = "text";
    selectionOverlay.style.webkitUserSelect = "text";
    selectionOverlay.style.whiteSpace = "pre";
    selectionOverlay.style.zIndex = "5";
    selectionOverlay.style.overflow = "hidden";
    selectionOverlay.style.pointerEvents = "auto"; // allow selection

    proxy.appendChild(content);
    proxy.appendChild(selectionOverlay);
    termDiv.appendChild(proxy);

    let isSyncing = false;
    const rowHeight = 16;
    let lastScrollTop = 50000;

    // Sync: Ghost -> Terminal (Passive & Momentum-Safe)
    proxy.addEventListener(
      "scroll",
      () => {
        if (isSyncing) return;

        const deltaScroll = proxy.scrollTop - lastScrollTop;
        const deltaLines = Math.round(deltaScroll / rowHeight);

        if (deltaLines !== 0) {
          if (tab.term.buffer.active.type === "alternate") {
            // In alternate buffer, send arrow keys to the terminal
            const seq = deltaLines < 0 ? "\x1b[A" : "\x1b[B";
            const count = Math.abs(deltaLines);
            for (let i = 0; i < count; i++) {
              emitPtyInput(tab, seq);
            }
          } else {
            tab.term.scrollLines(deltaLines);
          }
          lastScrollTop += deltaLines * rowHeight;
          selectionOverlay.style.top = proxy.scrollTop + "px";

          // Recenter periodically to prevent hitting bounds
          if (Math.abs(proxy.scrollTop - 50000) > 40000) {
            isSyncing = true;
            proxy.scrollTop = 50000;
            lastScrollTop = 50000;
            selectionOverlay.style.top = proxy.scrollTop + "px";
            setTimeout(() => {
              isSyncing = false;
            }, 10);
          }
        }
      },
      { passive: true },
    );

    // Tap-through logic: Only disable when a clear tap or long-press is detected
    let startX, startY;
    let touchStartTime = 0;
    proxy.addEventListener(
      "touchstart",
      (e) => {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        touchStartTime = Date.now();

        // Blur xterm's hidden textarea so the keyboard doesn't pop up instead of the selection menu
        if (tab.term && tab.term.textarea) {
          tab.term.textarea.blur();
        }

        // Populate selection overlay with visible terminal text
        let cellHeight = 16;
        let fontSizeStr = tab.term.options.fontSize + "px";
        let fontFamilyStr = tab.term.options.fontFamily;
        let letterSpacingStr = "normal";
        try {
          if (
            tab.term &&
            tab.term._core &&
            tab.term._core._renderService &&
            tab.term._core._renderService.dimensions &&
            tab.term._core._renderService.dimensions.css
          ) {
            cellHeight =
              tab.term._core._renderService.dimensions.css.cell.height;
          }
        } catch (e) {}

        const termRows = termDiv.querySelector(".xterm-rows");
        if (termRows) {
          const style = window.getComputedStyle(termRows);
          fontSizeStr = style.fontSize;
          fontFamilyStr = style.fontFamily;
          letterSpacingStr = style.letterSpacing;
        }

        selectionOverlay.style.lineHeight = cellHeight + "px";
        selectionOverlay.style.fontSize = fontSizeStr;
        selectionOverlay.style.fontFamily = fontFamilyStr;
        selectionOverlay.style.letterSpacing = letterSpacingStr;

        const screenElement = termDiv.querySelector(".xterm-screen");
        let offsetTop = 0;
        let offsetLeft = 0;
        if (screenElement) {
          const screenBox = screenElement.getBoundingClientRect();
          const proxyBox = proxy.getBoundingClientRect();
          // The canvas text baseline is slightly lower than a standard div's top-aligned text.
          // Nudge it down slightly (roughly 15% of cell height) to align the transparent text
          // perfectly over the canvas pixels so selections match visually.
          const baselineNudge = cellHeight * 0.15;
          offsetTop = screenBox.top - proxyBox.top + baselineNudge;
          offsetLeft = screenBox.left - proxyBox.left;
          selectionOverlay.style.width = screenElement.offsetWidth + "px";
        } else {
          selectionOverlay.style.width = "100%";
        }
        selectionOverlay.style.paddingTop = "0px";
        selectionOverlay.style.left = offsetLeft + "px";
        selectionOverlay.style.top = proxy.scrollTop + offsetTop + "px";

        const buffer = tab.term.buffer.active;
        const startRow = buffer.viewportY;
        const endRow = startRow + tab.term.rows;
        let textContent = "";
        for (let i = startRow; i < endRow; i++) {
          const line = buffer.getLine(i);
          if (line) {
            textContent += line.translateToString(true) + "\n";
          } else {
            textContent += "\n";
          }
        }
        selectionOverlay.textContent = filterTerminalFluff(textContent);
      },
      { passive: true },
    );

    proxy.addEventListener(
      "touchmove",
      (e) => {
        // Not doing much here now since selection uses native browser handling
      },
      { passive: true },
    );

    proxy.addEventListener(
      "touchend",
      (e) => {
        const deltaX = Math.abs(e.changedTouches[0].clientX - startX);
        const deltaY = Math.abs(e.changedTouches[0].clientY - startY);
        const duration = Date.now() - touchStartTime;

        if (deltaX < 10 && deltaY < 10 && duration < 300) {
          // This was a quick tap.
          // 1. Clear any active selection
          window.getSelection().removeAllRanges();

          // Temporarily hide proxy to find what's underneath
          proxy.style.display = "none";
          const underlying = document.elementFromPoint(
            e.changedTouches[0].clientX,
            e.changedTouches[0].clientY,
          );
          proxy.style.display = "block";

          if (underlying) {
            const eventInit = {
              view: window,
              bubbles: true,
              cancelable: true,
              clientX: e.changedTouches[0].clientX,
              clientY: e.changedTouches[0].clientY,
            };
            underlying.dispatchEvent(new MouseEvent("mousedown", eventInit));
            underlying.dispatchEvent(new MouseEvent("mouseup", eventInit));
            underlying.dispatchEvent(new MouseEvent("click", eventInit));
          }

          // 2. Focus the terminal with a tiny delay to allow link handling
          setTimeout(() => {
            if (tab.term) {
              if (
                tab.mobileProxy &&
                tab.mobileProxy.ui &&
                tab.mobileProxy.ui.proxyInput
              ) {
                tab.mobileProxy.ui.proxyInput.focus();
                tab.mobileProxy.ui.alignWithCursor(tab.term);
              } else if (
                document.activeElement !==
                document.querySelector("textarea.xterm-helper")
              ) {
                tab.term.focus();
              }
            }
          }, 50);

          // 3. Briefly disable pointer-events to let the tap through for focus
          proxy.style.pointerEvents = "none";
          setTimeout(() => {
            if (proxy) proxy.style.pointerEvents = "all";
          }, 150);
        }
      },
      { passive: true },
    );

    // Allow proxy to recover pointer events when clicking elsewhere or after selection
    document.addEventListener("selectionchange", () => {
      const selection = window.getSelection().toString();
      if (!selection && proxy.style.pointerEvents === "none") {
        // Selection cleared, safe to restore proxy
        proxy.style.pointerEvents = "all";
      }
    });

    // Set initial position
    proxy.scrollTop = 50000;
  }

  // Passive touch listener to ensure the browser doesn't wait for JS
  // before initiating a native scroll on the viewport.
  termDiv.addEventListener("touchmove", (e) => {}, { passive: true });

  // Improved Web Links support with wrapped line handling
  try {
    tab.term.registerLinkProvider({
      provideLinks(y, callback) {
        const buffer = tab.term.buffer.active;
        let startY = y - 1;

        // Find the start of the wrapped block
        while (startY > 0 && buffer.getLine(startY).isWrapped) {
          startY--;
        }

        // Assemble full text and keep track of line offsets
        let fullText = "";
        let lineOffsets = [0];
        let lineTexts = [];
        let currentY = startY;

        while (currentY < buffer.length) {
          const line = buffer.getLine(currentY);
          const lineText = line.translateToString(true);
          lineTexts.push(lineText);
          fullText += lineText;
          if (
            currentY + 1 < buffer.length &&
            !buffer.getLine(currentY + 1).isWrapped
          ) {
            break;
          }
          currentY++;
          lineOffsets.push(fullText.length);
        }

        const urlRegex = /https?:\/\/[^\s"'<>^`]+[^\s"'<>^`.,!?;:]/g;
        const links = [];
        let match;
        while ((match = urlRegex.exec(fullText)) !== null) {
          const uri = match[0];
          const matchStart = match.index;
          const matchEnd = match.index + uri.length;

          const lineIdx = y - 1 - startY;
          const lineStartOffset = lineOffsets[lineIdx];
          const lineEndOffset = lineStartOffset + lineTexts[lineIdx].length;

          if (matchEnd > lineStartOffset && matchStart < lineEndOffset) {
            const startX = Math.max(0, matchStart - lineStartOffset);
            const endX = Math.min(
              lineTexts[lineIdx].length,
              matchEnd - lineStartOffset,
            );

            links.push({
              text: uri, // Report the FULL uri even for this segment
              range: {
                start: { x: startX + 1, y: y },
                end: { x: endX, y: y },
              },
              activate: (e, text) => {
                console.log("LINK CLICKED: " + uri);
                window.open(uri, "_blank", "noopener,noreferrer");
              },
            });
          }
        }
        callback(links);
      },
    });
    debugLog("Custom LinkProvider registered.");
  } catch (e) {
    console.error("Failed to setup link provider:", e);
  }

  // Initialize Proxy Input Foundation for Mobile keyboards
  if (tab.term.textarea) {
    tab.mobileProxy = new MobileTerminalController(tab);
    // Handle image paste and text paste buffer clearing
    tab.term.textarea.addEventListener("paste", async (e) => {
      const items = (e.clipboardData || window.clipboardData)?.items;
      if (!items) return;
      let hasImage = false;
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type.startsWith("image/")) {
          hasImage = true;
          e.preventDefault();
          const file = item.getAsFile();
          if (!file) continue;

          const formData = new FormData();
          // Generate a generic filename if missing
          const ext = item.type.split("/")[1] || "png";
          formData.append(
            "file",
            file,
            file.name || `pasted-image-${Date.now()}.${ext}`,
          );

          try {
            const response = await fetchWithCSRF("/api/upload", {
              method: "POST",
              headers: {
                "X-CSRFToken": document
                  .querySelector('meta[name="csrf-token"]')
                  .getAttribute("content"),
              },
              body: formData,
            });
            if (!response.ok)
              throw new Error("Upload failed: " + response.statusText);
            const data = await response.json();
            sendToTerminal(`> I uploaded @${data.filename}\r`);
          } catch (error) {
            console.error("Paste upload error:", error);
            if (tab.term) {
              tab.term.write(
                `\r\n\x1b[31m[Error] Failed to upload pasted image: ${error.message}\x1b[0m\r\n`,
              );
            }
          }
        }
      }
      const isComposing = tab.mobileProxy?.ui?.isComposing || false;
      if (!hasImage && !isComposing) {
        // Normal text paste needs more time to process in xterm before clearing buffer
        setTimeout(() => {
          if (tab.term.textarea && tab.term.textarea.value.length > 0)
            tab.term.textarea.value = "";
        }, 100);
      }
    });
  }

  tab.socket = io.connect(window.location.origin, {
    auth: {
      csrf_token: document
        .querySelector('meta[name="csrf-token"]')
        ?.getAttribute("content"),
    },
    transports: ["websocket", "polling"],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
  });

  let disconnectTime = null;

  const handleConnect = async () => {
    disconnectTime = null;
    if (tab.term) {
      tab.term.clear();
    }
    tab.term.write("\r\n\x1b[2m[Connected to server]\x1b[0m\r\n");
    updateStatus(tab.session.ssh_target, tab.session.ssh_dir); // Restore correct status

    // Refresh CSRF token on reconnect in case server restarted
    try {
      await refreshCsrfToken();
    } catch (e) {
      console.error("Failed to refresh CSRF token:", e);
    }
    tab.socket.emit("join_room", { tab_id: tabId });
    tab.socket.emit("restart", {
      tab_id: tabId,
      reclaim: tab.shouldReclaim,
      sid: tab.socket.id,
      resume: tab.session.resume,
      cols: tab.term.cols,
      rows: tab.term.rows,
      ssh_target: target,
      ssh_dir: dir,
      mode: mode,
    });
    tab.shouldReclaim = true; // All subsequent reconnects should attempt reclaim

    setTimeout(() => {
      fitTerminal(tab);
      tab.term.focus();
    }, 150);
  };

  tab.socket.on("connect", handleConnect);

  if (tab.socket.connected) {
    handleConnect();
  }

  tab.socket.on("disconnect", (reason) => {
    disconnectTime = Date.now();
    tab.term.write(
      "\r\n\x1b[1;33m[Connection lost: " +
        reason +
        ". Attempting to reconnect...]\x1b[0m\r\n",
    );
    const statusEl = document.getElementById("connection-status");
    if (statusEl) {
      statusEl.innerText = "Reconnecting...";
      statusEl.style.color = "#e5e510"; // yellow
    }
    // Socket.io handles reconnection natively
    if (mode === "fake") {
      const modal = document.getElementById("friction-modal");
      if (modal) {
        modal.style.display = "flex";
      }
      tab.socket.disconnect(); // prevent auto-reconnect loops if we want friction modal interaction
    }
  });

  let reloadTimeout = null;

  tab.socket.on("reconnect", (attemptNumber) => {
    if (reloadTimeout) {
      clearTimeout(reloadTimeout);
      reloadTimeout = null;
    }
    tab.term.write(
      "\r\n\x1b[1;32m[Reconnected! Total attempts: " +
        attemptNumber +
        "]\x1b[0m\r\n",
    );
  });

  tab.socket.on("connect_error", async (error) => {
    if (error.message === "invalid_csrf") {
      if (tab.term) {
        tab.term.write("\r\n\x1b[1;33m[Securing connection...]\x1b[0m\r\n");
      }
      const newToken = await refreshCsrfToken();
      tab.socket.auth = { csrf_token: newToken };
      tab.socket.connect();
    }
  });

  tab.socket.on("reconnect_error", (error) => {
    // Keep retrying
  });

  tab.socket.on("reconnect_failed", () => {
    tab.term.write(
      "\r\n\x1b[1;31m[Reconnection failed. Will keep trying...]\x1b[0m\r\n",
    );
    tab.socket.connect();
  });

  tab.socket.on("session_assigned", (data) => {
    if (data.tab_id === tab.id && tab.session.resume === "new") {
      tab.session.resume = data.session_id.toString();
      saveTabsToStorage();
      localStorage.setItem("geminiResume", data.session_id.toString());
    }
  });

  tab.socket.on("session-terminated", () => {
    debugLog("Session terminated via tab socket:", tabId);
    closeTab(tabId, null, true);
  });

  tab.socket.on("session-dropped", () => {
    debugLog("Session dropped organically via tab socket:", tabId);
    if (tab.term) {
      tab.term.write(
        "\r\n\x1b[1;31m[Connection dropped unexpectedly. Reconnecting...]\x1b[0m\r\n",
      );
    }
    // Set a slight delay before reconnecting to avoid spam loops
    setTimeout(() => {
      if (tab.socket && tab.socket.connected) {
        tab.shouldReclaim = false; // We know it's dead, force fresh restart
        tab.socket.emit("restart", {
          tab_id: tabId,
          reclaim: false,
          sid: tab.socket.id,
          resume: tab.session.resume,
          cols: tab.term ? tab.term.cols : 80,
          rows: tab.term ? tab.term.rows : 24,
          ssh_target: tab.session.ssh_target,
          ssh_dir: tab.session.ssh_dir,
          mode: tab.session.type,
        });
      }
    }, 1500);
  });

  tab.socket.on("pty-output", (data) => {
    if (tab.term) {
      const buffer = tab.term.buffer.active;
      // If the user is at the bottom (or within 2 lines of it), we should ensure they stay at the bottom
      const isAtBottom = buffer.viewportY >= buffer.baseY - 2;
      tab.term.write(data.output, () => {
        // After writing, if they were at the bottom but xterm failed to keep them there, force it
        if (isAtBottom && buffer.viewportY < buffer.baseY) {
          tab.term.scrollToBottom();
        }
      });
    }
  });
  tab.socket.on("session-stolen", (data) => {
    tab.stolen = true;
    if (tab.socket) {
      tab.socket.disconnect();
    }
    if (tab.term) {
      tab.term.write(
        "\r\n\x1b[1;31m[Session stolen by another device. Click Reclaim to take it back.]\x1b[0m\r\n",
      );
    }
    if (activeTabId === tab.id) {
      const statusEl = document.getElementById("connection-status");
      if (statusEl) {
        statusEl.innerText = "Stolen";
        statusEl.style.color = "#c82424"; // red
      }
      const reclaimBtn = document.getElementById("reclaim-btn");
      if (reclaimBtn) reclaimBtn.style.display = "inline-block";
    }
  });
  tab.term.onData((data) => {
    if (tab.socket) {
      // Mobile modifiers are handled by MobileModifierState
      // Desktop modifiers are handled natively by xterm.js via e.ctrlKey
      if (window.emitPtyInput) window.emitPtyInput(tab, data);
      else emitPtyInput(tab, data);
    }
  });
  tab.term.onTitleChange((title) => {
    tab.title = title;
    if (tab.socket) {
      tab.socket.emit("update_title", { tab_id: tab.id, title: title });
    }
    renderTabs();
    updatePageTitle();

    // Trigger notification if action required (✋)
    if (title.includes("✋") && document.visibilityState !== "visible") {
      if ("Notification" in window && Notification.permission === "granted") {
        navigator.serviceWorker.ready.then((registration) => {
          registration.showNotification("Gemini Action Required", {
            body: title,
            icon: "/static/favicon.svg",
            tag: "gemini-action-" + tabId,
            renotify: true,
          });
        });
      }
    } else if (!title.includes("✋")) {
      if ("Notification" in window && navigator.serviceWorker) {
        navigator.serviceWorker.ready.then((registration) => {
          registration
            .getNotifications({ tag: "gemini-action-" + tabId })
            .then((notifications) => {
              notifications.forEach((notification) => notification.close());
            });
        });
      }
    }
  });
  tab.term.attachCustomKeyEventHandler((e) => {
    if (e.type === "keydown" && (e.ctrlKey || e.altKey) && e.key === "Enter") {
      if (tab.mobileProxy && tab.mobileProxy.ui) {
        tab.mobileProxy.ui.proxyInput.value += "\x1b\r";
        tab.mobileProxy.ui.proxyInput.dispatchEvent(
          new Event("input", { bubbles: true }),
        );
      } else {
        // Fallback for non-mobile if proxy isn't active
        if (tab.socket) emitPtyInput(tab, "\x1b\r");
      }
      return false;
    }

    // Allow printable characters and backspace to pass through to the textarea overlay
    // so they populate the autocorrect buffer instead of being swallowed by xterm's keydown handler.
    if (
      e.type === "keydown" &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.altKey &&
      e.key.length === 1
    ) {
      if (isMobile) return false;
    }
    if (e.type === "keydown" && e.key === "Backspace") {
      if (isMobile) return false;
    }

    return true;
  });
  renderTabs();
  switchTab(tabId);
}

function fitTerminal(tab) {
  if (!tab || tab.state !== "terminal" || !tab.term || !tab.fitAddon) return;
  const oldCols = tab.term.cols;
  const oldRows = tab.term.rows;
  try {
    tab.fitAddon.fit();
    if (tab.term.cols !== oldCols || tab.term.rows !== oldRows) {
      if (tab.socket && tab.socket.connected) {
        tab.socket.emit("resize", { cols: tab.term.cols, rows: tab.term.rows });
      }
    }
  } catch (e) {
    // Silently ignore fit errors during initialization (e.g. xterm-addon-fit dimensions getter throws)
  }
}

function triggerHapticFeedback() {
  if (navigator.vibrate) {
    navigator.vibrate(5);
  }
}

function emitPtyInput(tab, data) {
  if (!tab || !tab.socket || data == null) return;
  // Convert \n to \r so that bash processes STT newlines and multiline pastes as command submissions
  const strData = String(data).replace(/\n/g, "\r");
  tab.socket.emit("pty-input", { input: strData });
}
window.emitPtyInput = emitPtyInput;

function sendToTerminal(data) {
  const tab = tabs.find((t) => t.id === activeTabId);
  let finalData = data;

  if (tab && tab.mobileProxy && tab.mobileProxy.modifierState) {
    finalData = tab.mobileProxy.modifierState.applyModifiers(data);
  }

  if (tab && tab.socket && tab.state === "terminal") {
    emitPtyInput(tab, finalData);
    tab.term.focus();
  }
}
window.sendToTerminal = sendToTerminal;

function adjustFontSize(delta) {
  const tab = tabs.find((t) => t.id === activeTabId);
  if (tab && tab.term) {
    const newSize = Math.max(
      8,
      Math.min(40, tab.term.options.fontSize + delta),
    );
    tab.term.options.fontSize = newSize;
    currentFontSize = newSize;
    localStorage.setItem("gemini_font_size", currentFontSize);
    if (document.getElementById("theme-font")) {
      document.getElementById("theme-font").value = currentFontSize;
    }
    setTimeout(() => {
      fitTerminal(tab);
      if (tab.mobileProxy && tab.mobileProxy.ui) {
        tab.mobileProxy.ui.alignWithCursor(tab.term);
      }
    }, 50);
  }
}

function switchTab(id) {
  activeTabId = id;
  window.activeTabId = id;
  const tab = tabs.find((t) => t.id === id);
  if (!tab) return;

  if (launcherRefreshInterval) {
    clearInterval(launcherRefreshInterval);
    launcherRefreshInterval = null;
  }

  if (tab.state === "launcher") {
    // Trigger a refresh and restart polling when switching back to launcher
    // We don't re-render the whole launcher, just the dynamic parts if they exist
    const refreshBtn = document.getElementById(`${id}_backend_sessions`);
    if (refreshBtn) {
      refreshBackendSessionsList(id);

      fetch("/api/hosts")
        .then((r) => r.json())
        .then((hosts) => {
          hosts.forEach((conn, index) => {
            const sessionListId = `${id}_sessions_${conn.label.replace(
              /[^a-z0-9]/gi,
              "",
            )}`;
            setTimeout(() => {
              fetchSessions(id, conn, sessionListId, false, false);
            }, index * 500);
          });

          if (launcherRefreshInterval) clearInterval(launcherRefreshInterval);
          launcherRefreshInterval = setInterval(() => {
            refreshBackendSessionsList(id);
            hosts.forEach((conn, index) => {
              const sessionListId = `${id}_sessions_${conn.label.replace(
                /[^a-z0-9]/gi,
                "",
              )}`;
              setTimeout(() => {
                fetchSessions(id, conn, sessionListId, false, false, true);
              }, index * 500);
            });
          }, 10000);
        });
    }
  }

  document
    .querySelectorAll(".tab-instance")
    .forEach((el) => el.classList.remove("active"));
  const inst = document.getElementById(id + "_instance");
  if (inst) inst.classList.add("active");
  document
    .querySelectorAll(".tab")
    .forEach((el) => el.classList.remove("active"));
  const nav = document.getElementById("nav-" + id);
  if (nav) nav.classList.add("active");
  const toolbarInfo = document.getElementById("active-connection-info");
  const mobileControls = document.getElementById("mobile-controls");
  saveTabsToStorage();

  if (tab.state === "terminal") {
    toolbarInfo.style.display = "flex";
    const reclaimBtn = document.getElementById("reclaim-btn");
    if (reclaimBtn)
      reclaimBtn.style.display = tab.stolen ? "inline-block" : "none";
    mobileControls.style.display = isMobile ? "grid" : "none";
    updateStatus(tab.session.ssh_target, tab.session.ssh_dir);
    if (tab.stolen) {
      const statusEl = document.getElementById("connection-status");
      if (statusEl) {
        statusEl.innerText = "Stolen";
        statusEl.style.color = "#c82424";
      }
    }
    setTimeout(() => {
      fitTerminal(tab);
      if (tab.term) {
        tab.term.focus();
      }
      tabs.forEach((t) => {
        if (t.mobileProxy && t.mobileProxy.ui && t.term) {
          t.mobileProxy.ui.alignWithCursor(t.term);
        }
      });
    }, 50);
  } else {
    toolbarInfo.style.display = "none";
    mobileControls.style.display = "none";
    updateStatus("picker");
  }
}

function reclaimStolenSession() {
  const tab = tabs.find((t) => t.id === activeTabId);
  if (tab && tab.stolen) {
    tab.stolen = false;
    const reclaimBtn = document.getElementById("reclaim-btn");
    if (reclaimBtn) reclaimBtn.style.display = "none";
    if (tab.socket) {
      tab.socket.connect();
      updateStatus(tab.session.ssh_target, tab.session.ssh_dir);
    }
  }
}

function restartActiveTab() {
  const tab = tabs.find((t) => t.id === activeTabId);
  if (tab && tab.state === "terminal") {
    const { ssh_target, ssh_dir, resume } = tab.session;
    tab.term.clear();
    tab.socket.emit("restart", {
      tab_id: tab.id,
      resume: resume,
      cols: tab.term.cols,
      rows: tab.term.rows,
      ssh_target: ssh_target,
      ssh_dir: ssh_dir,
      mode: mode,
    });
    updateStatus(ssh_target, ssh_dir);
  }
}

function closeTab(id, event, isLocalOnly = false) {
  if (event) event.stopPropagation();
  const index = tabs.findIndex((t) => t.id === id);
  if (index === -1) return;
  const tab = tabs[index];
  if (tab.state === "launcher") return; // Cannot close the launcher (+ New) tab

  if (!isLocalOnly) {
    // 1. Emit targeted WebSocket termination event
    if (tab.socket && tab.socket.connected) {
      debugLog("Emitting terminate_session via WebSocket for tab: " + id);
      tab.socket.emit("terminate_session", { tab_id: id });
    }

    // 2. HTTP Fallback
    // Explicitly terminate backend session
    fetchWithCSRF(`/api/management/sessions/${id}`, {
      method: "DELETE",
    }).then((resp) => {
      if (!resp.ok && resp.status !== 404) {
        resp.json().then((data) => {
          debugLog("Termination failed for " + id + ": " + data.error);
        });
      }
    });
  }

  if (tab.socket) tab.socket.disconnect();
  if (tab.webglAddon) {
    try {
      tab.webglAddon.dispose();
    } catch (e) {}
  }
  if (tab.term) tab.term.dispose();
  const inst = document.getElementById(id + "_instance");
  if (inst) inst.remove();
  tabs.splice(index, 1);
  if (tabs.length === 0) addNewTab();
  else {
    if (activeTabId === id) switchTab(tabs[Math.max(0, index - 1)].id);
    renderTabs();
  }
  saveTabsToStorage();
  updatePageTitle();
}

function renderTabs() {
  const bar = document.getElementById("tab-bar");
  bar.innerHTML = "";
  tabs.forEach((tab) => {
    const el = document.createElement("div");
    el.id = "nav-" + tab.id;
    el.className = "tab" + (tab.id === activeTabId ? " active" : "");
    el.title = tab.title; // Add tooltip for full tab name
    el.onclick = () => switchTab(tab.id);

    // Support for right-click context menu
    el.oncontextmenu = (e) => {
      e.preventDefault();
      showTabContextMenu(tab.id, e.clientX, e.clientY);
    };

    // Support for long-press on mobile
    let longPressTimer;
    el.ontouchstart = (e) => {
      longPressTimer = setTimeout(() => {
        showTabContextMenu(tab.id, e.touches[0].clientX, e.touches[0].clientY);
      }, 500);
    };
    el.ontouchend = () => clearTimeout(longPressTimer);
    el.ontouchmove = () => clearTimeout(longPressTimer);

    el.innerHTML =
      `<span>${tab.title}</span>` +
      (tab.state === "launcher"
        ? ""
        : `<span class="tab-close" data-onclick="closeTab('${tab.id}', event, false)">&times;</span>`);
    bar.appendChild(el);
  });
}

function showTabContextMenu(id, x, y) {
  // Remove existing menu if any
  const existingMenu = document.getElementById("tab-context-menu");
  if (existingMenu) existingMenu.remove();

  const menu = document.createElement("div");
  menu.id = "tab-context-menu";
  menu.className = "context-menu js-style-87d2f1"; // Shared style for menus
  menu.style.left = x + "px";
  menu.style.top = y + "px";

  const tab = tabs.find((t) => t.id === id);
  if (!tab) {
    return;
  }

  const sections = [
    {
      title: "Tab Actions",
      items: [
        { label: "New Tab", action: () => addNewTab() },
        {
          label: "Rename Tab",
          action: () => {
            const newTitle = prompt("Enter new tab title:", tab.title);
            if (newTitle) {
              tab.title = newTitle;
              renderTabs();
              saveTabsToStorage();
            }
          },
        },
        {
          label: "Close Tab",
          action: () => closeTab(id, null, false),
          hide: tab.state === "launcher",
        },
      ],
    },
    {
      title: "Prompts",
      items: [
        ...DEFAULT_PROMPTS.map((p) => ({
          label: p.name,
          action: () => sendPromptToTab(id, p.text),
        })),
        ...getCustomPrompts().map((p) => ({
          label: p.name,
          action: () => sendPromptToTab(id, p.text),
        })),
      ],
      hide: tab.state !== "terminal",
    },
    {
      title: "Manage",
      items: [
        { label: "Add Prompt", action: () => openAddPromptModal() },
        { label: "Manage Prompts", action: () => openManagePromptsModal() },
      ],
    },
  ];

  sections.forEach((section) => {
    if (section.hide) return;

    const header = document.createElement("div");
    header.className = "context-menu-section-header";
    header.innerText = section.title;
    menu.appendChild(header);

    section.items.forEach((opt) => {
      if (opt.hide) return;
      const item = document.createElement("div");
      item.className = "context-menu-item";
      item.innerText = opt.label;
      item.onclick = () => {
        opt.action();
        menu.remove();
      };
      menu.appendChild(item);
    });
  });

  document.body.appendChild(menu);

  // Close menu on click outside
  const closeMenu = (e) => {
    if (!menu.contains(e.target)) {
      menu.remove();
      document.removeEventListener("click", closeMenu);
    }
  };
  setTimeout(() => document.addEventListener("click", closeMenu), 10);
}

let resizeObserverTimeout;
const resizeObserver = new ResizeObserver(() => {
  clearTimeout(resizeObserverTimeout);
  resizeObserverTimeout = setTimeout(() => {
    tabs.forEach((tab) => fitTerminal(tab));
  }, 50);
});
resizeObserver.observe(document.getElementById("terminal-container"));

// Abstract visualViewport so it can be mocked in tests
window.appVisualViewport = window.visualViewport
  ? {
      get height() {
        return window.visualViewport.height;
      },
      get scale() {
        return window.visualViewport.scale;
      },
      get offsetTop() {
        return window.visualViewport.offsetTop;
      },
      get offsetLeft() {
        return window.visualViewport.offsetLeft;
      },
      addEventListener: window.visualViewport.addEventListener.bind(
        window.visualViewport,
      ),
      removeEventListener: window.visualViewport.removeEventListener.bind(
        window.visualViewport,
      ),
    }
  : null;

// Handle mobile keyboard resizing using Visual Viewport API
if (window.appVisualViewport) {
  let resizeTimeout;
  let lastViewHeight = window.appVisualViewport.height;

  const updateViewport = () => {
    if (window.appVisualViewport.scale > 1.05) {
      return; // User is zooming, do not break layout
    }

    const viewHeight = window.appVisualViewport.height;
    const offsetTop = window.appVisualViewport.offsetTop || 0;

    // Use a CSS variable for height for smoother rendering across components
    document.documentElement.style.setProperty("--vh", `${viewHeight}px`);

    // Lock body to the visible viewport height to prevent scrolling past keyboard
    document.body.style.height = `${viewHeight}px`;

    // On iOS Safari, the visual viewport moves independently of the layout viewport.
    // We counteract this by positioning the body exactly where the visual viewport is.
    if (Math.abs(offsetTop) > 0.1) {
      document.body.style.top = `${offsetTop}px`;
      // Prevent browser from trying to scroll the layout viewport
      if (window.scrollY !== 0) {
        window.scrollTo(0, 0);
      }
    } else {
      document.body.style.top = "0";
    }
  };

  window.appVisualViewport.addEventListener("resize", () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      if (window.appVisualViewport.scale > 1.05) {
        return; // User is zooming, do not break layout
      }
      const viewHeight = window.appVisualViewport.height;
      // Ignore tiny jitters (less than 10px) to prevent scroll interruption
      if (Math.abs(viewHeight - lastViewHeight) < 10) return;
      lastViewHeight = viewHeight;

      updateViewport();
      tabs.forEach((tab) => {
        fitTerminal(tab);
        // Immediate alignment of proxy input after xterm resizes
        if (tab.mobileProxy && tab.mobileProxy.ui && tab.term) {
          tab.mobileProxy.ui.alignWithCursor(tab.term);
        }
      });
    }, 60); // Faster response time for snappier keyboard feel
  });

  window.appVisualViewport.addEventListener("scroll", updateViewport);

  // Also initialize with the current height
  updateViewport();
}
if (mode === "fake" && sessionId) {
  document.body.classList.add("theme-fake-session");
  const id = "tab_" + (Date.now() + Math.floor(Math.random() * 1000));
  const tab = {
    id,
    term: null,
    fitAddon: null,
    socket: null,
    session: null,
    title: "Test Session",
    state: "terminal",
  };
  tabs.push(tab);

  const container = document.createElement("div");
  container.id = id + "_instance";
  container.className = "tab-instance active";
  document.getElementById("terminal-container").appendChild(container);

  activeTabId = id;
  renderTabs();
  startSession(id, "local", "", "", sessionId, "Test Session", true);

  const modalHtml = `
                <div class="friction-modal js-style-224b51" id="friction-modal">
                    <div class="friction-modal-content">
                        <h2>Session Disconnected</h2>
                        <p>The test session has ended or disconnected.</p>
                        <div class="friction-actions">
                            <button class="primary" data-onclick="window.location.href='/test-launcher'">Start Fresh Test</button>
                            <button class="danger" data-onclick="forceReconnect()">Force Reconnect</button>
                        </div>
                    </div>
                </div>
            `;
  document.body.insertAdjacentHTML("beforeend", modalHtml);

  window.forceReconnect = () => {
    document.getElementById("friction-modal").style.display = "none";
    const currentTab = tabs.find((t) => t.id === activeTabId);
    if (currentTab && currentTab.socket) {
      currentTab.socket.connect();
    }
  };

  window.addEventListener("beforeunload", (e) => {
    document.getElementById("friction-modal").style.display = "flex";
    e.preventDefault();
    e.returnValue = "";
  });
} else if (deepHost || deepTarget) {
  // GEMWEBUI-311: Deep link handling
  const id = "tab_" + (Date.now() + Math.floor(Math.random() * 1000));
  const tab = {
    id,
    term: null,
    fitAddon: null,
    socket: null,
    session: null,
    title: deepHost || deepTarget.split("@").pop(),
    state: "terminal",
  };
  tabs.push(tab);

  const container = document.createElement("div");
  container.id = id + "_instance";
  container.className = "tab-instance active";
  document.getElementById("terminal-container").appendChild(container);

  activeTabId = id;
  renderTabs();

  if (deepHost) {
    fetch("/api/hosts")
      .then((r) => r.json())
      .then((hosts) => {
        const host = hosts.find((h) => h.label === deepHost);
        if (host) {
          startSession(
            id,
            host.type,
            host.target || "",
            deepDir || host.dir || "",
            false,
            host.label,
          );
        } else {
          // Fallback to launcher if host not found
          closeTab(id);
          addNewTab();
          alert("Deep link host not found: " + deepHost);
        }
      })
      .catch((err) => {
        console.error("Deep link host fetch failed", err);
        closeTab(id);
        addNewTab();
      });
  } else {
    // deepTarget
    startSession(
      id,
      "ssh",
      deepTarget,
      deepDir || "",
      false,
      deepTarget.split("@").pop(),
    );
  }
} else if (!loadTabsFromStorage()) {
  addNewTab(true);
}

// --- Quick Connect Logic ---
let currentQuickTabId = null;
let currentQuickHost = null;

function parseQuickInput(val) {
  if (!val) return null;
  // Format: user@host[:port] [directory]

  let user = "";
  let host = "";
  let port = "";
  let folder = "~";

  // 1. Split by space for directory
  const spaceIdx = val.indexOf(" ");
  if (spaceIdx !== -1) {
    folder = val.substring(spaceIdx + 1).trim() || "~";
    val = val.substring(0, spaceIdx).trim();
  }

  // 2. Split for user/host
  const userParts = val.split("@");
  if (userParts.length > 1) {
    user = userParts[0];
    val = userParts[1];
  } else {
    return null; // User is required
  }

  // 3. Split for host/port
  const hostParts = val.split(":");
  host = hostParts[0];
  if (hostParts.length > 1) {
    port = hostParts[1];
  }

  if (!host) return null;

  return {
    label: host,
    type: "ssh",
    target: port ? `${user}@${host}:${port}` : `${user}@${host}`,
    dir: folder,
  };
}

async function saveHost(host) {
  await fetch("/api/hosts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(host),
  });
}

function quickConnectAction(tabId, action) {
  const input = document.getElementById(tabId + "_quick_input");
  const host = parseQuickInput(input.value);
  if (!host)
    return alert(
      "Invalid format. Use user@host, user@host:port, or user@host/folder",
    );

  currentQuickTabId = tabId;
  currentQuickHost = host;

  if (action === "key") {
    document.getElementById("quick-add-host-info").innerText =
      `Connecting to: ${host.target}`;
    document.getElementById("quick-add-key-modal").style.display = "block";
  } else {
    // Just connect
    saveHost(host).then(() => {
      startSession(tabId, host.type, host.target, host.dir, false);
    });
  }
}

function closeQuickAddKey() {
  document.getElementById("quick-add-key-modal").style.display = "none";
}

async function submitQuickAddKey() {
  const name = document.getElementById("quick-key-name").value;
  const text = document.getElementById("quick-key-text").value;
  if (!name || !text) return alert("Key name and text required");

  // 1. Save Key
  await fetch("/api/keys/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, key: text }),
  });

  // 2. Save Host
  await saveHost(currentQuickHost);

  // 3. Close and Connect
  closeQuickAddKey();
  startSession(
    currentQuickTabId,
    currentQuickHost.type,
    currentQuickHost.target,
    currentQuickHost.dir,
    false,
  );
}
// --- End Quick Connect Logic ---

// --- Modal Management ---
let modalMouseDownTarget = null;
const settingsModal = document.getElementById("settings-modal");
const quickAddModal = document.getElementById("quick-add-key-modal");
const shareModal = document.getElementById("share-modal");
const previewModal = document.getElementById("preview-modal");

[settingsModal, quickAddModal, shareModal, previewModal].forEach((modal) => {
  if (!modal) return;
  modal.addEventListener("mousedown", (e) => {
    modalMouseDownTarget = e.target;
  });
  modal.addEventListener("mouseup", (e) => {
    if (modalMouseDownTarget === modal && e.target === modal) {
      if (modal === settingsModal) closeSettings();
      else if (modal === quickAddModal) closeQuickAddKey();
      else if (modal === shareModal) closeShareModal();
      else if (modal === previewModal) closePreviewModal();
    }
    modalMouseDownTarget = null;
  });
});

async function openSettings() {
  document.getElementById("settings-modal").style.display = "block";
  loadHosts();
  loadKeys();
  loadPublicKey();
  initThemeUI();
  loadSharedSessions();
}

async function loadSharedSessions() {
  const list = document.getElementById("shared-sessions-list");
  if (!list) return;
  list.innerHTML =
    '<div class="js-style-a06f1d">Loading session snapshots...</div>';
  try {
    const response = await fetch("/api/shares");
    if (response.ok) {
      const data = await response.json();
      const shares = data.shares || data; // handle if it's wrapped or array directly

      list.innerHTML = "";
      if (!shares || shares.length === 0) {
        list.innerHTML =
          '<div class="js-style-a674a2">No session snapshots.</div>';
        return;
      }

      // Note: API might return an object with keys or array, handle accordingly
      const shareArray = Array.isArray(shares)
        ? shares
        : Object.keys(shares).map((k) => ({ id: k, ...shares[k] }));

      shareArray.forEach((share) => {
        const item = document.createElement("div");
        item.className = "session-item";
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.alignItems = "center";
        item.style.borderBottom = "1px solid #444";
        item.style.padding = "10px";

        const dateStr = share.created_at
          ? new Date(share.created_at * 1000).toLocaleString()
          : "Unknown";
        const shareId = share.id || share.uuid; // handle both just in case
        const linkUrl = window.location.origin + "/s/" + shareId;
        const sessionName = share.session_name || "Session Snapshot";

        item.innerHTML = `
                            <div class="js-style-b2fad5">
                                <div class="js-style-68bda4">${sessionName}</div>
                                <div class="js-style-339053">Created: ${dateStr}</div>
                            </div>
                            <div class="js-style-611fa3">
                                <button class="primary small" data-onclick="viewSharedSession('${shareId}')">View</button>
                                <button class="success small" data-onclick="copyToClipboard('${linkUrl}')">Copy</button>
                                <button class="danger small" data-onclick="deleteSharedSession('${shareId}')">Delete</button>
                            </div>
                        `;
        list.appendChild(item);
      });
    } else {
      list.innerHTML =
        '<div class="js-style-808abb">Failed to load session snapshots.</div>';
    }
  } catch (e) {
    console.error("Failed to load session snapshots", e);
    list.innerHTML =
      '<div class="js-style-808abb">Error loading session snapshots.</div>';
  }
}

async function deleteSharedSession(uuid) {
  if (!confirm("Are you sure you want to delete this session snapshot?"))
    return;
  try {
    const response = await fetch("/api/shares/" + uuid, {
      method: "DELETE",
      headers: {
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
    });
    if (response.ok) {
      loadSharedSessions();
    } else {
      const data = await response.json();
      alert("Failed to delete: " + (data.error || "Unknown error"));
    }
  } catch (e) {
    console.error("Failed to delete session snapshot", e);
    alert("Error deleting session snapshot.");
  }
}

function viewSharedSession(uuid) {
  const previewModal = document.getElementById("preview-modal");
  const iframe = document.getElementById("preview-iframe");
  if (previewModal && iframe) {
    iframe.src = "/s/" + uuid;
    previewModal.style.display = "block";
  }
}

function closePreviewModal() {
  const previewModal = document.getElementById("preview-modal");
  const iframe = document.getElementById("preview-iframe");
  if (previewModal) {
    previewModal.style.display = "none";
  }
  if (iframe) {
    iframe.src = ""; // Clear iframe to stop loading
  }
}

async function loadPublicKey() {
  try {
    const response = await fetch("/api/keys/public");
    if (response.ok) {
      const data = await response.json();
      document.getElementById("public-key-text").innerText = data.key;
      document.getElementById("instance-key-snippet").innerText =
        `mkdir -p ~/.ssh && echo "${data.key}" >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`;
      document.getElementById("public-key-container").style.display = "block";
    }
  } catch (e) {
    console.error("Could not load public key", e);
  }
}

function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard
      .writeText(text)
      .then(() => alert("Copied to clipboard"));
  } else {
    // Fallback for non-secure contexts (dev environments)
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand("copy");
      alert("Copied to clipboard (fallback mode)");
    } catch (err) {
      console.error("Fallback copy failed", err);
      alert("Copy failed. Please copy manually.");
    }
    document.body.removeChild(textArea);
  }
}

function copyPublicKey() {
  copyToClipboard(document.getElementById("public-key-text").innerText);
}
function copyInstanceSnippet() {
  copyToClipboard(document.getElementById("instance-key-snippet").innerText);
}
async function rotateInstanceKey() {
  if (
    !confirm(
      "Are you sure you want to rotate the instance key? All remote hosts using the current key will lose access until updated with the new one.",
    )
  )
    return;
  try {
    const response = await fetch("/api/keys/rotate", { method: "POST" });
    if (response.ok) {
      const data = await response.json();
      alert("Instance key rotated successfully.");
      loadPublicKey(); // Refresh UI
    } else {
      const err = await response.json();
      alert("Error rotating key: " + err.message);
    }
  } catch (e) {
    console.error("Rotate failed", e);
  }
}
class EnvVarManager {
  constructor() {
    this.container = document.getElementById("env-vars-list");
    this.addBtn = document.getElementById("add-env-var-btn");
    this.addBtn.addEventListener("click", () => this.addVariable());
    this.variables = [];
  }

  addVariable(key = "", value = "") {
    const row = document.createElement("div");
    row.style.display = "flex";
    row.style.gap = "5px";

    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.placeholder = "Key (e.g. PORT)";
    keyInput.value = key;
    keyInput.style.flex = "1";

    const valInput = document.createElement("input");
    valInput.type = "text";
    valInput.placeholder = "Value";
    valInput.value = value;
    valInput.style.flex = "1";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "danger small";
    removeBtn.innerText = "X";
    removeBtn.onclick = () => {
      this.container.removeChild(row);
    };

    row.appendChild(keyInput);
    row.appendChild(valInput);
    row.appendChild(removeBtn);
    this.container.appendChild(row);
  }

  clear() {
    this.container.innerHTML = "";
  }

  load(envVars) {
    this.clear();
    if (envVars) {
      for (const [key, value] of Object.entries(envVars)) {
        this.addVariable(key, value);
      }
    }
  }

  get() {
    const envVars = {};
    for (let i = 0; i < this.container.children.length; i++) {
      const row = this.container.children[i];
      const key = row.children[0].value.trim();
      const value = row.children[1].value.trim();
      if (key) {
        envVars[key] = value;
      }
    }
    return envVars;
  }
}

let envVarManager;
document.addEventListener("DOMContentLoaded", async () => {
  try {
    await refreshCsrfToken();
  } catch (e) {
    console.error("Failed to initialize CSRF token:", e);
  }
  envVarManager = new EnvVarManager();
  await loadPromptsFromServer();
});

async function fetchWithCSRF(url, options = {}) {
  options.headers = options.headers || {};
  options.headers["X-CSRFToken"] =
    document
      .querySelector('meta[name="csrf-token"]')
      ?.getAttribute("content") || "";
  options.skipCsrfReload = true; // Prevent global fetch from reloading page on 400/403

  let response = await fetch(url, options);

  if (response.status === 400 || response.status === 403) {
    try {
      const newToken = await refreshCsrfToken();
      options.headers["X-CSRFToken"] = newToken;
      response = await fetch(url, options);
    } catch (e) {
      console.error("Failed to refresh CSRF token on retry:", e);
    }
  }
  return response;
}

let editingHostLabel = null;

async function loadHosts() {
  const hosts = await (await fetch("/api/hosts")).json();
  const list = document.getElementById("hosts-list");
  list.innerHTML = "";
  hosts.forEach((host) => {
    const item = document.createElement("div");
    item.className = "session-item";
    item.style.cursor = "pointer";
    item.onclick = () => populateHostForm(host);
    item.innerHTML =
      `<div class="session-info"><span class="js-style-7160a4">${
        host.label
      }</span><span class="js-style-c27a65">${host.target || "local"} ${
        host.dir || ""
      }</span></div>` +
      (host.label !== "local"
        ? `<button class="danger small" data-onclick="event.stopPropagation(); removeHost('${host.label}')">Delete</button>`
        : "");
    list.appendChild(item);
  });
}
function populateHostForm(host) {
  document.getElementById("new-host-label").value = host.label;
  document.getElementById("new-host-target").value = host.target || "";
  document.getElementById("new-host-dir").value = host.dir || "";
  if (envVarManager) envVarManager.load(host.env_vars || {});
  if (host.label === "local") {
    editingHostLabel = null;
    setHostMode("add"); // Cannot edit default local, force add mode
  } else {
    editingHostLabel = host.label;
    setHostMode("edit");
  }
}
function setHostMode(mode) {
  const addBtn = document.getElementById("add-mode-btn");
  const editBtn = document.getElementById("edit-mode-btn");
  const submitBtn = document.getElementById("add-host-btn");
  const labelInput = document.getElementById("new-host-label");

  if (mode === "edit") {
    if (labelInput.value === "local") {
      alert(
        "The default 'local' host cannot be edited. It will be used as a template for a new host.",
      );
      setHostMode("add");
      return;
    }
    addBtn.style.opacity = "0.5";
    addBtn.style.fontWeight = "normal";
    editBtn.style.opacity = "1";
    editBtn.style.fontWeight = "bold";
    submitBtn.innerText = "Update Host";
    submitBtn.className = "primary";
  } else {
    editingHostLabel = null;
    addBtn.style.opacity = "1";
    addBtn.style.fontWeight = "bold";
    editBtn.style.opacity = "0.5";
    editBtn.style.fontWeight = "normal";
    submitBtn.innerText = "Add Host";
    submitBtn.className = "success";
  }
}
function clearHostForm() {
  document.getElementById("new-host-label").value = "";
  document.getElementById("new-host-target").value = "";
  document.getElementById("new-host-dir").value = "";
  if (envVarManager) envVarManager.clear();
  editingHostLabel = null;
  setHostMode("add");
}
async function submitHostForm() {
  const label = document.getElementById("new-host-label").value;
  const target = document.getElementById("new-host-target").value;
  const dir = document.getElementById("new-host-dir").value;
  const submitBtn = document.getElementById("add-host-btn");

  if (!label) return alert("Label required");
  if (label === "local" && submitBtn.innerText === "Update Host") {
    return alert("Cannot update protected 'local' host.");
  }

  const host = {
    label,
    type: target ? "ssh" : "local",
    target,
    dir,
    env_vars: envVarManager ? envVarManager.get() : {},
    old_label: editingHostLabel, // Pass to server for in-place update
  };
  const response = await fetch("/api/hosts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(host),
  });

  if (response.ok) {
    const originalText = submitBtn.innerText;
    submitBtn.innerText = originalText + " ✓";
    setTimeout(() => {
      submitBtn.innerText = originalText;
    }, 2000);

    editingHostLabel = label; // Update current tracking
    loadHosts();
  } else {
    alert("Failed to save host.");
  }
}
async function removeHost(label) {
  if (!confirm(`Remove host ${label}?`)) return;
  await fetch(`/api/hosts/${encodeURIComponent(label)}`, { method: "DELETE" });
  loadHosts();
}
async function loadKeys() {
  const keys = await (await fetch("/api/keys")).json();
  const list = document.getElementById("key-list");
  list.innerHTML = "";
  if (keys.length === 0)
    list.innerHTML = '<li class="js-style-52b0fe">No keys found.</li>';
  keys.forEach((key) => {
    const li = document.createElement("li");
    li.className = "session-item";
    li.innerHTML = `<div class="session-info">${key}</div><button class="danger small" data-onclick="removeKey('${key}')">Delete</button>`;
    list.appendChild(li);
  });
}
async function removeKey(filename) {
  if (!confirm(`Delete key ${filename}?`)) return;
  await fetch(`/api/keys/${filename}`, { method: "DELETE" });
  loadKeys();
}
function closeSettings() {
  document.getElementById("settings-modal").style.display = "none";
  tabs.forEach((t) => {
    if (t.state === "launcher") renderLauncher(t.id);
  });
}

function exportSettings() {
  window.location.href = "/api/settings/export";
}

function importSettings(event) {
  const file = event.target.files[0];
  if (!file) return;

  if (
    !confirm(
      "Warning: Importing settings will overwrite your current configuration. Are you sure you want to proceed?",
    )
  ) {
    event.target.value = "";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  fetch("/api/settings/import", {
    method: "POST",
    body: formData,
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        alert(
          "Settings imported successfully. The application will now reload.",
        );
        window.location.reload();
      } else {
        alert("Failed to import settings: " + (data.error || "Unknown error"));
      }
    })
    .catch((err) => {
      console.error(err);
      alert("An error occurred during import.");
    })
    .finally(() => {
      event.target.value = "";
    });
}
async function savePastedKey() {
  const name = document.getElementById("ssh-key-name").value;
  const text = document.getElementById("ssh-key-text").value;
  if (!name || !text) return alert("Name and key text required");
  await fetch("/api/keys/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, key: text }),
  });
  document.getElementById("ssh-key-name").value = "";
  document.getElementById("ssh-key-text").value = "";
  loadKeys();
}

async function uploadKeyFile() {
  const fileInput = document.getElementById("ssh-key-file");
  if (!fileInput.files.length) return alert("Please select a file to upload");
  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetchWithCSRF("/api/keys/upload", {
      method: "POST",
      headers: {
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
      body: formData,
    });

    if (response.ok) {
      fileInput.value = "";
      loadKeys();
    } else {
      let errorMessage = "Unknown error";
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.indexOf("application/json") !== -1) {
        try {
          const data = await response.json();
          errorMessage = data.error || data.message || errorMessage;
        } catch (e) {
          errorMessage = "Failed to parse error response.";
        }
      } else {
        errorMessage = await response.text();
      }
      if (response.status === 400 || response.status === 403) {
        errorMessage += " (Auth/CSRF error - please reload the page)";
      }
      alert("Upload failed: " + errorMessage);
    }
  } catch (err) {
    alert("Upload failed: " + err.message);
  }
}

// Prevent iOS/Android pull-to-refresh or page slide when swiping on controls
const mobileControlsContainer = document.getElementById("mobile-controls");
if (mobileControlsContainer) {
  mobileControlsContainer.addEventListener(
    "touchmove",
    (e) => {
      e.preventDefault();
    },
    { passive: false },
  );
}

// Setup Hold-to-Repeat for mobile buttons
document.querySelectorAll(".control-btn.holdable").forEach((btn) => {
  let timeoutId = null;
  let intervalId = null;
  let isActive = false;

  const executeAction = (e) => {
    let cmd = btn.getAttribute("data-cmd");
    const adjust = btn.getAttribute("data-func-adjust");
    if (cmd) {
      // Unescape characters like \x1b and \t from the DOM attribute string
      cmd = cmd.replace(/\\x([0-9A-Fa-f]{2})/g, (match, hex) =>
        String.fromCharCode(parseInt(hex, 16)),
      );
      cmd = cmd.replace(/\\t/g, "\t");
      cmd = cmd.replace(/\\r/g, "\r");
      cmd = cmd.replace(/\\n/g, "\n");

      // Handle Shift modifier toggle from MobileModifierState for Tab key
      const isShift =
        (e && e.shiftKey) ||
        (typeof MobileModifierState !== "undefined" &&
          MobileModifierState.instance &&
          MobileModifierState.instance.shiftActive);

      if (cmd === "\t" && isShift) {
        cmd = "\x1b[Z";
        if (
          MobileModifierState.instance &&
          MobileModifierState.instance.shiftActive
        ) {
          MobileModifierState.instance.toggleShift(false);
        }
      }
      window.sendToTerminal(cmd);
    }
    if (adjust) {
      adjustFontSize(parseInt(adjust));
    }
  };

  const startAction = (e) => {
    if (e.type === "touchstart") {
      e.preventDefault(); // prevent mouse emulation and selection
      triggerHapticFeedback();
    }
    if (isActive) return;
    isActive = true;

    // Add visual feedback
    btn.style.opacity = "0.7";

    executeAction(e);

    // Delay before repeating
    timeoutId = setTimeout(() => {
      // Repeat rate
      intervalId = setInterval(() => {
        triggerHapticFeedback();
        executeAction(e);
      }, 40);
    }, 250);
  };

  const stopAction = (e) => {
    if (e && e.type === "touchend") e.preventDefault();
    isActive = false;
    btn.style.opacity = "1";
    clearTimeout(timeoutId);
    clearInterval(intervalId);
  };

  btn.addEventListener("mousedown", startAction);
  btn.addEventListener("touchstart", startAction, { passive: false });

  btn.addEventListener("mouseup", stopAction);
  btn.addEventListener("mouseleave", stopAction);
  btn.addEventListener("touchend", stopAction);
  btn.addEventListener("touchcancel", stopAction);
});

function openFileTransfer() {
  document.getElementById("file-transfer-modal").style.display = "block";
}

function closeFileTransfer() {
  document.getElementById("file-transfer-modal").style.display = "none";
}

function shareSession() {
  const tab = tabs.find((t) => t.id === activeTabId);
  if (!tab || tab.state !== "terminal")
    return alert("No active terminal to share.");
  document.getElementById("share-result").style.display = "none";
  document.getElementById("confirm-share-btn").style.display = "block";
  document.getElementById("share-modal").style.display = "block";
}

function closeShareModal() {
  document.getElementById("share-modal").style.display = "none";
}

async function confirmShareSession() {
  const tab = tabs.find((t) => t.id === activeTabId);
  if (!tab || !tab.term) return;

  document.getElementById("confirm-share-btn").style.display = "none";

  let serializeAddon;
  try {
    serializeAddon = new SerializeAddon.SerializeAddon();
    tab.term.loadAddon(serializeAddon);
  } catch (e) {
    console.error("Failed to load serialize addon", e);
    alert("Serialize addon could not be loaded.");
    return;
  }

  const selectedTheme = "full";

  let htmlDump = serializeAddon.serializeAsHTML({
    includeGlobalBackground: false,
  });

  // Fix missing '#' in truecolor hex values generated by xterm-addon-serialize
  htmlDump = htmlDump.replace(/color:\s*([0-9a-fA-F]{6})/g, "color: #$1");

  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = htmlDump;

  // Xterm serialization usually wraps in a single root element
  const rootEl = tempDiv.firstElementChild || tempDiv;
  const lines = Array.from(rootEl.children);

  // Trim trailing empty lines to prevent massive whitespace
  while (lines.length > 0) {
    const lastLine = lines[lines.length - 1];
    if (
      !lastLine.textContent ||
      !lastLine.textContent.replace(/\u00a0/g, " ").trim()
    ) {
      lastLine.remove();
      lines.pop();
    } else {
      break;
    }
  }

  // Remove explicit color styles from the root container so CSS themes can apply
  for (const child of tempDiv.children) {
    if (child.style) {
      child.style.backgroundColor = "";
      child.style.color = "";
    }
  }
  const preDiv = tempDiv.querySelector("pre > div");
  if (preDiv && preDiv.style) {
    preDiv.style.backgroundColor = "";
    preDiv.style.color = "";
  }
  htmlDump = tempDiv.innerHTML;

  try {
    const response = await fetch("/api/shares/create", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
      body: JSON.stringify({
        html_content: htmlDump,
        session_name: tab.title || tab.session.ssh_target || "Local Session",
        theme: selectedTheme,
      }),
    });

    const result = await response.json();
    if (response.ok && result.share_url) {
      document.getElementById("share-result").style.display = "block";
      document.getElementById("share-link-input").value =
        window.location.origin + result.share_url;
    } else {
      alert("Failed to share: " + (result.error || "Unknown error"));
      document.getElementById("confirm-share-btn").style.display = "block";
    }
  } catch (err) {
    alert("Share error: " + err.message);
    document.getElementById("confirm-share-btn").style.display = "block";
  } finally {
    serializeAddon.dispose();
  }
}

function copyShareLink() {
  const linkInput = document.getElementById("share-link-input");
  linkInput.select();
  linkInput.setSelectionRange(0, 99999);
  copyToClipboard(linkInput.value);
}

async function uploadPastedImage(file, tab, terminalEmitCallback) {
  const formData = new FormData();
  const ext = file.type ? file.type.split("/")[1] || "png" : "png";
  const filename = `pasted_images/pasted-image-${Date.now()}.${ext}`;
  formData.append("file", file, filename);

  if (tab && tab.session && tab.session.type === "ssh") {
    if (!tab.session.ssh_target) {
      terminalEmitCallback(
        "\r\n\x1b[31m[Error] SSH target is missing from session state! Upload cannot proceed.\x1b[0m\r\n",
      );
      return;
    }
    formData.append("ssh_target", tab.session.ssh_target);
    if (tab.session.ssh_dir) {
      formData.append("ssh_dir", tab.session.ssh_dir);
    }
  }

  try {
    const csrfToken =
      document
        .querySelector('meta[name="csrf-token"]')
        ?.getAttribute("content") || "";
    // Using standard fetch with CSRF header to ensure compatibility
    const response = await fetch("/api/upload", {
      method: "POST",
      headers: csrfToken ? { "X-CSRFToken": csrfToken } : {},
      body: formData,
    });

    if (!response.ok) throw new Error("Upload failed: " + response.statusText);
    const data = await response.json();
    terminalEmitCallback(`> I pasted @${data.filename}\r`);
  } catch (error) {
    console.error("Paste upload error:", error);
    terminalEmitCallback(
      `\r\n\x1b[31m[Error] Failed to upload pasted image: ${error.message}\x1b[0m\r\n`,
    );
  }
}

async function uploadWorkspaceFile() {
  const fileInput = document.getElementById("workspace-upload-file");
  if (!fileInput.files.length) return alert("Please select a file to upload");

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const tab = tabs.find((t) => t.id === activeTabId);
  if (tab && tab.session && tab.session.type === "ssh") {
    if (!tab.session.ssh_target) {
      alert("SSH target is missing from session state! Upload cannot proceed.");
      return;
    }
    formData.append("ssh_target", tab.session.ssh_target);
    if (tab.session.ssh_dir) {
      formData.append("ssh_dir", tab.session.ssh_dir);
    }
  }

  try {
    const response = await fetchWithCSRF("/api/upload", {
      method: "POST",
      headers: {
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
      body: formData,
    });
    const result = await response.json();
    if (result.status === "success") {
      const tab = tabs.find((t) => t.id === activeTabId);
      if (tab && tab.socket && tab.state === "terminal") {
        emitPtyInput(tab, `> I uploaded @${result.filename}\r`);
        tab.term.focus();
      } else {
        alert("File uploaded successfully");
      }
      closeFileTransfer();
      fileInput.value = "";
    } else {
      alert("Upload failed: " + result.message);
    }
  } catch (err) {
    alert("Upload error: " + err.message);
  }
}

const wsDownloadInput = document.getElementById("workspace-download-filename");
const autocompleteResults = document.getElementById("autocomplete-results");
let downloadDebounceTimer;

wsDownloadInput.addEventListener("input", () => {
  clearTimeout(downloadDebounceTimer);
  autocompleteResults.style.display = "none";

  downloadDebounceTimer = setTimeout(async () => {
    const q = wsDownloadInput.value;
    const tab = tabs.find((t) => t.id === activeTabId);

    if (!tab || tab.session.type !== "ssh" || !q) {
      return;
    }

    try {
      const response = await fetch(
        `/api/sessions/${tab.id}/search_files?q=${encodeURIComponent(q)}`,
      );
      if (!response.ok) throw new Error("Failed to fetch autocomplete");
      const data = await response.json();

      autocompleteResults.innerHTML = "";
      if (data.matches && data.matches.length > 0) {
        data.matches.forEach((match) => {
          const item = document.createElement("div");
          item.className = "autocomplete-item";
          item.textContent = match;
          item.onclick = () => {
            if (match.endsWith("/")) {
              wsDownloadInput.value = match;
              wsDownloadInput.focus();
              wsDownloadInput.dispatchEvent(new Event("input"));
            } else {
              wsDownloadInput.value = match;
              autocompleteResults.style.display = "none";
            }
          };
          autocompleteResults.appendChild(item);
        });
        autocompleteResults.style.display = "block";
      }
    } catch (e) {
      console.error("Autocomplete search error:", e);
    }
  }, 300);
});

// Hide autocomplete on click outside
document.addEventListener("click", (e) => {
  if (e.target !== wsDownloadInput && e.target !== autocompleteResults) {
    autocompleteResults.style.display = "none";
  }
});

function downloadWorkspaceFile() {
  const filenameInput = document.getElementById("workspace-download-filename");
  const filename = filenameInput.value.trim();
  if (!filename) return alert("Please enter a filename");

  window.location.href = `/api/download/${encodeURIComponent(filename)}`;
  closeFileTransfer();
  filenameInput.value = "";
}

// --- Drag and Drop Feature ---
const dropZone = document.createElement("div");
dropZone.className = "drop-zone";
dropZone.innerText = "Drop files here to upload";
document.body.appendChild(dropZone);

document.addEventListener("dragover", (e) => {
  const activeTab = tabs.find((t) => t.id === activeTabId);
  if (!activeTab || activeTab.state !== "terminal") return;
  e.preventDefault();
  dropZone.classList.add("active");
});

document.addEventListener("dragleave", (e) => {
  const activeTab = tabs.find((t) => t.id === activeTabId);
  if (!activeTab || activeTab.state !== "terminal") return;
  e.preventDefault();
  if (e.target === dropZone || e.relatedTarget === null) {
    dropZone.classList.remove("active");
  }
});

document.addEventListener("drop", async (e) => {
  const activeTab = tabs.find((t) => t.id === activeTabId);
  if (!activeTab || activeTab.state !== "terminal") return;
  e.preventDefault();
  dropZone.classList.remove("active");

  async function traverseFileTree(item, path = "") {
    return new Promise((resolve) => {
      if (item.isFile) {
        item.file((file) => {
          resolve([{ file, path: path + file.name }]);
        });
      } else if (item.isDirectory) {
        const dirReader = item.createReader();
        dirReader.readEntries(async (entries) => {
          let files = [];
          for (let i = 0; i < entries.length; i++) {
            const subFiles = await traverseFileTree(
              entries[i],
              path + item.name + "/",
            );
            files = files.concat(subFiles);
          }
          resolve(files);
        });
      } else {
        resolve([]);
      }
    });
  }

  let allFiles = [];
  if (e.dataTransfer.items) {
    const promises = [];
    for (let i = 0; i < e.dataTransfer.items.length; i++) {
      const item = e.dataTransfer.items[i].webkitGetAsEntry();
      if (item) {
        promises.push(traverseFileTree(item));
      }
    }
    const results = await Promise.all(promises);
    allFiles = results.flat();
  } else if (e.dataTransfer.files) {
    for (let i = 0; i < e.dataTransfer.files.length; i++) {
      allFiles.push({
        file: e.dataTransfer.files[i],
        path: e.dataTransfer.files[i].name,
      });
    }
  }

  if (allFiles.length > 0) {
    let successCount = 0;
    let lastFilename = "";

    let uploadPrefix = "";
    if (allFiles.length > 1) {
      uploadPrefix = `upload-${Math.floor(Date.now() / 1000)}/`;
    }

    for (const { file, path } of allFiles) {
      const finalPath = uploadPrefix + path;
      const formData = new FormData();
      formData.append("file", file, finalPath);

      const tab = activeTab;
      if (tab && tab.session && tab.session.type === "ssh") {
        if (!tab.session.ssh_target) {
          alert(
            "SSH target is missing from session state! Upload cannot proceed.",
          );
          return;
        }
        formData.append("ssh_target", tab.session.ssh_target);
        if (tab.session.ssh_dir) {
          formData.append("ssh_dir", tab.session.ssh_dir);
        }
      }

      try {
        const response = await fetchWithCSRF("/api/upload", {
          method: "POST",
          headers: {
            "X-CSRFToken":
              document
                .querySelector('meta[name="csrf-token"]')
                ?.getAttribute("content") || "",
          },
          body: formData,
        });
        const result = await response.json();
        if (result.status === "success") {
          successCount++;
          lastFilename = result.filename;
        } else {
          alert(`Upload failed for ${finalPath}: ` + result.message);
        }
      } catch (err) {
        alert(`Upload error for ${finalPath}: ` + err.message);
      }
    }

    if (successCount > 0) {
      const tab = tabs.find((t) => t.id === activeTabId);
      if (tab && tab.socket && tab.state === "terminal") {
        const msg =
          successCount > 1
            ? `> I uploaded multiple files to @${uploadPrefix}\r`
            : `> I uploaded @${lastFilename}\r`;
        emitPtyInput(tab, msg);
        tab.term.focus();
      } else if (successCount === 1) {
        alert("File uploaded successfully");
      } else {
        alert(`${successCount} files uploaded successfully`);
      }
    }
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const fileTransferModal = document.getElementById("file-transfer-modal");
    const dropZone = document.querySelector(".drop-zone");
    if (
      (fileTransferModal && fileTransferModal.style.display === "block") ||
      (dropZone && dropZone.classList.contains("active"))
    ) {
      if (fileTransferModal) closeFileTransfer();
      if (dropZone) dropZone.classList.remove("active");
      return;
    }

    const settingsModal = document.getElementById("settings-modal");
    if (settingsModal && settingsModal.style.display === "block") {
      closeSettings();
      return;
    }

    const activeTab = tabs.find((t) => t.id === activeTabId);
    if (activeTab && activeTab.state === "launcher" && tabs.length > 1) {
      const otherTab =
        tabs.find((t) => t.id !== activeTabId && t.state === "terminal") ||
        tabs.find((t) => t.id !== activeTabId);
      if (otherTab) {
        switchTab(otherTab.id);
      }
      return;
    }
  }
});

let desktopContextMenuInitialized = false;
function initDesktopContextMenu() {
  if (isMobile || desktopContextMenuInitialized) return;
  desktopContextMenuInitialized = true;

  const menu = document.createElement("div");
  menu.id = "desktop-context-menu";
  menu.className = "desktop-context-menu";
  menu.innerHTML = `
    <div class="menu-item" id="ctx-copy">Copy</div>
    <div class="menu-item" id="ctx-paste">Paste</div>
  `;
  document.body.appendChild(menu);

  menu.querySelector("#ctx-copy").addEventListener("mousedown", (e) => {
    e.preventDefault();
    const tab = tabs.find((t) => t.id === activeTabId);
    if (tab && tab.term && tab.term.hasSelection()) {
      const selectedText = tab.term.getSelection();
      navigator.clipboard.writeText(filterTerminalFluff(selectedText));
    } else {
      document.execCommand("copy");
    }
    menu.style.display = "none";
  });

  menu.querySelector("#ctx-paste").addEventListener("mousedown", async (e) => {
    e.preventDefault();
    try {
      let text = await navigator.clipboard.readText();
      const tab = tabs.find((t) => t.id === activeTabId);
      if (tab && tab.socket) {
        const useBracketedPaste =
          tab.term && tab.term.modes && tab.term.modes.bracketedPasteMode;
        if (useBracketedPaste) {
          text = "\x1b[200~" + text + "\x1b[201~";
        }
        if (window.emitPtyInput) {
          window.emitPtyInput(tab, text);
        } else {
          tab.socket.emit("pty-input", {
            input: text,
          });
        }
      }
    } catch (err) {
      console.error("Paste failed", err);
    }
    menu.style.display = "none";
  });

  document.addEventListener("mousedown", (e) => {
    if (
      menu.style.display === "block" &&
      !e.target.closest("#desktop-context-menu")
    ) {
      menu.style.display = "none";
    }
  });
}

// --- Installation Recommendation Banner ---
function checkInstallationStatus() {
  // Check if running as a standalone app (installed PWA)
  const isInstalled =
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone ||
    document.referrer.includes("android-app://");

  const isDismissed =
    localStorage.getItem("install_banner_dismissed") === "true";

  if (!isInstalled && !isDismissed) {
    const banner = document.getElementById("install-banner");
    if (banner) banner.style.display = "flex";
  } else {
    const banner = document.getElementById("install-banner");
    if (banner) banner.style.display = "none";
  }
}

function dismissInstallBanner() {
  const banner = document.getElementById("install-banner");
  if (banner) banner.style.display = "none";
  localStorage.setItem("install_banner_dismissed", "true");
}

// Run the check on load
document.addEventListener("DOMContentLoaded", checkInstallationStatus);
// Also run it immediately in case DOMContentLoaded already fired
if (
  document.readyState === "complete" ||
  document.readyState === "interactive"
) {
  checkInstallationStatus();
}

// --- Prompts Modals ---
function openAddPromptModal(index = -1) {
  currentEditPromptIndex = index;
  const nameInput = document.getElementById("new-prompt-name");
  const textInput = document.getElementById("new-prompt-text");
  const title = document.getElementById("prompt-modal-title");

  if (index >= 0) {
    const prompts = getCustomPrompts();
    nameInput.value = prompts[index].name;
    textInput.value = prompts[index].text;
    if (title) title.innerText = "Edit Prompt";
  } else {
    nameInput.value = "";
    textInput.value = "";
    if (title) title.innerText = "Add Prompt";
  }
  document.getElementById("add-prompt-modal").style.display = "block";
}

function closeAddPromptModal() {
  document.getElementById("add-prompt-modal").style.display = "none";
}

function openManagePromptsModal() {
  renderPromptsList();
  document.getElementById("manage-prompts-modal").style.display = "block";
}

function closeManagePromptsModal() {
  document.getElementById("manage-prompts-modal").style.display = "none";
}

function renderPromptsList() {
  const listEl = document.getElementById("prompts-list");
  const prompts = getCustomPrompts();

  if (prompts.length === 0) {
    listEl.innerHTML =
      '<div class="auto-style-8d107b">No custom prompts added yet.</div>';
    return;
  }

  let html = "";
  prompts.forEach((p, index) => {
    html += `
      <div class="prompt-manage-item">
        <div class="prompt-manage-info">
          <div class="prompt-manage-name">${p.name}</div>
          <div class="prompt-manage-text">${p.text}</div>
        </div>
        <div class="prompt-manage-actions">
          <button class="small primary" data-onclick="openAddPromptModal(${index})">Edit</button>
          <button class="small danger" data-onclick="deletePrompt(${index})">Delete</button>
        </div>
      </div>
    `;
  });
  listEl.innerHTML = html;
}

async function deletePrompt(index) {
  if (confirm("Are you sure you want to delete this prompt?")) {
    const prompt = customPrompts[index];
    if (!prompt || !prompt.id) return;

    try {
      const response = await fetchWithCSRF(`/api/prompts/${prompt.id}`, {
        method: "DELETE",
      });
      if (response.ok) {
        await loadPromptsFromServer();
        renderPromptsList();
      }
    } catch (e) {
      console.error("Failed to delete prompt:", e);
    }
  }
}

async function saveNewPrompt() {
  const name = document.getElementById("new-prompt-name").value.trim();
  const text = document.getElementById("new-prompt-text").value.trim();

  if (!name || !text) {
    alert("Please provide both a name and a prompt.");
    return;
  }

  const payload = { name, text };
  if (currentEditPromptIndex >= 0) {
    payload.id = customPrompts[currentEditPromptIndex].id;
  }

  try {
    const response = await fetchWithCSRF("/api/prompts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (response.ok) {
      await loadPromptsFromServer();
      closeAddPromptModal();
      if (
        document.getElementById("manage-prompts-modal").style.display ===
        "block"
      ) {
        renderPromptsList();
      }
    }
  } catch (e) {
    console.error("Failed to save prompt:", e);
  }
}

// CSP Event Delegation
function executeDataAction(code, event) {
  if (!code) return;

  if (code === "document.getElementById('import-settings-input').click()") {
    document.getElementById("import-settings-input").click();
    return;
  }
  if (code === "window.location.href='/test-launcher'") {
    window.location.href = "/test-launcher";
    return;
  }
  if (code.includes("event.stopPropagation();")) {
    event.stopPropagation();
    code = code.replace("event.stopPropagation();", "").trim();
  }
  if (
    code ===
    "window.open(document.getElementById('share-link-input').value, '_blank')"
  ) {
    window.open(document.getElementById("share-link-input").value, "_blank");
    return;
  }
  if (
    code ===
    "document.getElementById('connection-issue-modal').style.display='none'"
  ) {
    document.getElementById("connection-issue-modal").style.display = "none";
    return;
  }
  if (code === "window.location.reload()") {
    window.location.reload();
    return;
  }
  if (code.startsWith("window.expandedSessionLists")) {
    let m1 = code.match(/expandedSessionLists\.(add|delete)\('([^']+)'\)/);
    if (m1) {
      if (m1[1] === "add") window.expandedSessionLists.add(m1[2]);
      else window.expandedSessionLists.delete(m1[2]);
    }
    let m2 = code.match(
      /fetchSessions\('([^']*)',\s*(\{.*\}),\s*'([^']*)',\s*(true|false),\s*true,\s*true\)/,
    );
    if (m2) {
      let b1 = m2[4] === "true";
      window.fetchSessions(
        m2[1],
        JSON.parse(m2[2].replace(/&quot;/g, '"')),
        m2[3],
        b1,
        true,
        true,
      );
    }
    return;
  }

  let match = code.match(/^([a-zA-Z0-9_]+)\((.*)\)$/);
  if (match) {
    let funcName = match[1];
    let argsStr = match[2];
    let args = [];
    if (argsStr.trim()) {
      let inString = false;
      let quoteChar = "";
      let currentArg = "";
      let braceCount = 0;
      let bracketCount = 0;
      for (let i = 0; i < argsStr.length; i++) {
        let char = argsStr[i];
        if (inString) {
          if (char === quoteChar && argsStr[i - 1] !== "\\") inString = false;
          currentArg += char;
        } else {
          if (char === "'" || char === '"') {
            inString = true;
            quoteChar = char;
            currentArg += char;
          } else if (char === "{") {
            braceCount++;
            currentArg += char;
          } else if (char === "}") {
            braceCount--;
            currentArg += char;
          } else if (char === "[") {
            bracketCount++;
            currentArg += char;
          } else if (char === "]") {
            bracketCount--;
            currentArg += char;
          } else if (char === "," && braceCount === 0 && bracketCount === 0) {
            args.push(currentArg);
            currentArg = "";
          } else {
            currentArg += char;
          }
        }
      }
      args.push(currentArg);

      args = args.map((s) => {
        s = s.trim();
        if (s === "event") return event;
        if (s === "true") return true;
        if (s === "false") return false;
        if (s.startsWith("'") && s.endsWith("'"))
          return s.slice(1, -1).replace(/\\'/g, "'").replace(/\\\\/g, "\\");
        if (s.startsWith('"') && s.endsWith('"'))
          return s
            .slice(1, -1)
            .replace(/\\"/g, '"')
            .replace(/\\\\/g, "\\")
            .replace(/&quot;/g, '"');
        if (!isNaN(s) && s !== "") return Number(s);
        if (s.startsWith("{") || s.startsWith("[")) {
          try {
            return JSON.parse(s.replace(/&quot;/g, '"'));
          } catch (err) {}
        }
        return s;
      });
    }

    if (typeof window[funcName] === "function") {
      window[funcName].apply(null, args);
    } else {
      console.error("Function not found: " + funcName);
    }
  } else {
    console.error("Could not parse data action: " + code);
  }
}

document.addEventListener("click", function (e) {
  let target = e.target.closest("[data-onclick]");
  if (target) {
    executeDataAction(target.getAttribute("data-onclick"), e);
  }
});

document.addEventListener("change", function (e) {
  let target = e.target.closest("[data-onchange]");
  if (target) {
    executeDataAction(target.getAttribute("data-onchange"), e);
  }
});

// Task Monitor
async function openTaskMonitor() {
  document.getElementById("task-monitor-modal").style.display = "block";
  await refreshTaskMonitor();
}

function closeTaskMonitor() {
  document.getElementById("task-monitor-modal").style.display = "none";
}

async function refreshTaskMonitor() {
  const list = document.getElementById("task-monitor-list");
  list.innerHTML = "Loading tasks...";
  try {
    const res = await fetch("/api/tasks", {
      headers: { Authorization: `Bearer ${localStorage.getItem("api_key")}` },
    });
    if (!res.ok) throw new Error("Failed to fetch tasks");
    const data = await res.json();

    let html = "";
    for (const [user, tasks] of Object.entries(data)) {
      html += `<h4>User: ${escapeHtml(user)}</h4>`;
      if (tasks.length === 0) {
        html += `<p>No active tasks</p>`;
      } else {
        html += `<table style="width:100%; text-align:left; border-collapse: collapse;">
          <tr>
            <th style="border-bottom: 1px solid #444; padding: 5px;">Name</th>
            <th style="border-bottom: 1px solid #444; padding: 5px;">Target</th>
            <th style="border-bottom: 1px solid #444; padding: 5px;">PID</th>
            <th style="border-bottom: 1px solid #444; padding: 5px;">Started/Last Seen</th>
            <th style="border-bottom: 1px solid #444; padding: 5px;">Status</th>
            <th style="border-bottom: 1px solid #444; padding: 5px;">Action</th>
          </tr>`;
        for (const t of tasks) {
          const dateStr = new Date(t.last_seen * 1000).toLocaleString();
          html += `<tr>
            <td style="padding: 5px;">${escapeHtml(t.title || "Unknown")}</td>
            <td style="padding: 5px;">${escapeHtml(
              t.ssh_target || "Local",
            )}</td>
            <td style="padding: 5px;">${escapeHtml(String(t.pid))}</td>
            <td style="padding: 5px;">${escapeHtml(dateStr)}</td>
            <td style="padding: 5px;">${t.active ? "Active" : "Dead"}</td>
            <td style="padding: 5px;">
              <button class="small danger" data-onclick="killTask('${
                t.tab_id
              }', ${t.pid})">Kill</button>
            </td>
          </tr>`;
        }
        html += `</table>`;
      }
    }
    list.innerHTML = html || "<p>No active connections found.</p>";
  } catch (err) {
    list.innerHTML = `<p style="color:red">Error: ${err.message}</p>`;
  }
}

async function killTask(tabId, pid) {
  if (!confirm(`Are you sure you want to kill process ${pid}?`)) return;
  console.log(
    `[Task Monitor] Attempting to kill task with PID ${pid} (Tab ID: ${tabId})...`,
  );
  try {
    const res = await fetch("/api/tasks/kill", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("api_key")}`,
      },
      body: JSON.stringify({ tab_id: tabId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to kill task");

    console.log(`[Task Monitor] Successfully killed PID ${pid}.`);
    // Refresh the list
    await refreshTaskMonitor();
  } catch (err) {
    console.error(`[Task Monitor] Error killing task ${pid}:`, err);
    alert(`Failed to kill task: ${err.message}`);
  }
}
