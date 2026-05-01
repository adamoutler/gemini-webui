// src/static/js/core/state.js

/**
 * Global application state
 * Encapsulated in an object so we can mutate it across modules without 'Assignment to constant variable' errors
 */
export const state = {
  tabs: [],
  activeTabId: null,
  customPrompts: [],
  currentEditPromptIndex: -1,
  ctrlActive: false,
  altActive: false,
  initialAutoResumeDone: false,
  launcherRefreshInterval: null,
  titleFlashInterval: null,
  originalPageTitle: "Gemini WebUI",
  wakeLock: null,
};

export const DEFAULT_PROMPTS = [
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

const urlParams = new URLSearchParams(window.location.search);
export const URL_PARAMS = {
  mode: urlParams.get("mode"),
  sessionId: urlParams.get("session_id"),
  deepHost: urlParams.get("host"),
  deepTarget: urlParams.get("target"),
  deepDir: urlParams.get("dir"),
};

// Debug Configuration
window.ENABLE_DEBUG = localStorage.getItem("GEMINI_DEBUG") === "true";

export function setDebug(enabled) {
  window.ENABLE_DEBUG = !!enabled;
  if (enabled) {
    localStorage.setItem("GEMINI_DEBUG", "true");
    console.log("Verbose debugging enabled. To disable, run: setDebug(false)");
  } else {
    localStorage.removeItem("GEMINI_DEBUG");
    console.log("Verbose debugging disabled. To enable, run: setDebug(true)");
  }
}
window.setDebug = setDebug;

export function debugLog(...args) {
  if (window.ENABLE_DEBUG) {
    console.log(...args);
  }
}

export const HostStateManager = {
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
