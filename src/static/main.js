import { initializeTheme, terminalTheme } from "./js/ui/theme.js";

import {
  loadTabsFromServer,
  syncTabs,
  loadTabsFromStorage,
  addNewTab,
  showTabContextMenu,
  renderTabs,
  switchTab,
  closeTab,
  restartActiveTab,
  saveTabsToStorage,
} from "./js/ui/tabs.js";
import {
  openSettings,
  closeSettings,
  loadSharedSessions,
  deleteSharedSession,
  viewSharedSession,
  closePreviewModal,
  loadPublicKey,
  copyPublicKey,
  rotateInstanceKey,
  loadHosts,
  populateHostForm,
  setHostMode,
  clearHostForm,
  submitHostForm,
  removeHost,
  loadKeys,
  removeKey,
  exportSettings,
  importSettings,
  savePastedKey,
  uploadKeyFile,
} from "./js/ui/settings.js";
import {
  openFileTransfer,
  closeFileTransfer,
  uploadWorkspaceFile,
  downloadWorkspaceFile,
  uploadPastedImage,
  openAddPromptModal,
  closeAddPromptModal,
  openManagePromptsModal,
  closeManagePromptsModal,
  renderPromptsList,
  deletePrompt,
  saveNewPrompt,
  shareSession,
  closeShareModal,
  confirmShareSession,
  copyShareLink,
  openTaskMonitor,
  closeTaskMonitor,
  refreshTaskMonitor,
  killTask,
} from "./js/ui/modals.js";
import {
  createTerminalContainer,
  recreateTerminalUI,
  startSession,
  fitTerminal,
} from "./js/terminal/ui.js";
export { createTerminalContainer, recreateTerminalUI, fitTerminal };
import {
  emitPtyInput,
  sendToTerminal,
  adjustFontSize,
} from "./js/terminal/pty.js";
export { emitPtyInput };
import {
  globalState,
  DEFAULT_PROMPTS,
  loadPromptsFromServer,
  getCustomPrompts,
} from "./js/core/state.js";
import {
  escapeHtml,
  filterTerminalFluff,
  setDebug,
  debugLog,
  customFetch,
  originalFetch,
} from "./js/core/api.js";

// SendPromptToTab functionality needs global state access:
export function sendPromptToTab(tabId, text) {
  const tab = globalState.tabs.find((t) => t.id === tabId);
  if (tab?.socket && tab.state === "terminal") {
    const input =
      text.endsWith("\n") || text.endsWith("\r") ? text : text + "\r";
    tab.socket.emit("pty-input", {
      input: input,
    });
  } else {
    alert("Tab is not connected to a terminal.");
  }
}
globalThis.sendPromptToTab = sendPromptToTab;

// PWA Service Worker Registration
if ("serviceWorker" in navigator) {
  globalThis.addEventListener("load", () => {
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
globalThis.addEventListener("beforeinstallprompt", (e) => {
  debugLog("beforeinstallprompt event fired");
  // e.preventDefault(); // Don't prevent default, we want the browser prompt
});
globalThis.addEventListener("appinstalled", (evt) => {
  debugLog("Gemini WebUI was installed");
});

// Request Notification Permission
if (
  "Notification" in globalThis.window &&
  Notification.permission === "default"
) {
  document.addEventListener(
    "click",
    () => {
      if (Notification.permission === "default") {
        Notification.requestPermission();
      }
    },
    {
      once: true,
    },
  );
}

import { EventBus } from "./js/core/event-bus.js";
import {
  updateWakeLock,
  updatePageTitle,
  checkInstallationStatus,
  dismissInstallBanner,
  initDesktopContextMenu,
} from "./js/core/pwa-system.js";
import { getGlobalSocket } from "./js/core/socket.js";
import { HostStateManager, updateStatus } from "./js/ui/launcher.js";
import {
  parseQuickInput,
  saveHost,
  quickConnectAction,
  closeQuickAddKey,
  submitQuickAddKey,
  copyInstanceSnippet,
} from "./js/ui/quick-connect.js";
import { triggerHapticFeedback } from "./js/mobile/mobile-input-extra.js";
import {
  refreshBackendSessionsList,
  terminateBackendSession,
  terminateAllBackendSessions,
  reclaimBackendSession,
  fetchSessions,
  parseSessions,
  reclaimStolenSession,
  renderLauncher,
} from "./js/core/session-manager.js";
import { fetchWithCSRF } from "./js/core/api.js";

import {
  openAutomationDashboard,
  closeAutomationDashboard,
  switchAutomationTab,
  saveAutomationSchedule,
  deleteAutomationSchedule,
  executeAutomationSchedule,
} from "./js/ui/automation.js";

const Actions = {
  updateWakeLock,
  updateHostHealthIndicator:
    HostStateManager.updateHealth.bind(HostStateManager),
  updatePageTitle,
  loadTabsFromServer,
  syncTabs,
  createTerminalContainer,
  saveTabsToStorage,
  loadTabsFromStorage,
  recreateTerminalUI,
  updateStatus,
  addNewTab,
  refreshBackendSessionsList,
  renderLauncher,
  terminateBackendSession,
  terminateAllBackendSessions,
  reclaimBackendSession,
  getGlobalSocket,
  fetchSessions,
  parseSessions,
  startSession,
  fitTerminal,
  triggerHapticFeedback,
  emitPtyInput,
  sendToTerminal,
  adjustFontSize,
  switchTab,
  reclaimStolenSession,
  restartActiveTab,
  closeTab,
  renderTabs,
  showTabContextMenu,
  parseQuickInput,
  saveHost,
  quickConnectAction,
  closeQuickAddKey,
  submitQuickAddKey,
  openSettings,
  loadSharedSessions,
  deleteSharedSession,
  viewSharedSession,
  closePreviewModal,
  loadPublicKey,
  copyToClipboard: (text) => {
    navigator.clipboard.writeText(text);
  },
  copyPublicKey,
  copyInstanceSnippet,
  rotateInstanceKey,
  fetchWithCSRF,
  loadHosts,
  populateHostForm,
  setHostMode,
  clearHostForm,
  submitHostForm,
  removeHost,
  loadKeys,
  removeKey,
  closeSettings,
  exportSettings,
  importSettings,
  savePastedKey,
  uploadKeyFile,
  openFileTransfer,
  closeFileTransfer,
  shareSession,
  closeShareModal,
  confirmShareSession,
  copyShareLink,
  uploadPastedImage,
  uploadWorkspaceFile,
  downloadWorkspaceFile,
  initDesktopContextMenu,
  checkInstallationStatus,
  dismissInstallBanner,
  openAddPromptModal,
  closeAddPromptModal,
  openManagePromptsModal,
  closeManagePromptsModal,
  renderPromptsList,
  deletePrompt,
  saveNewPrompt,
  openTaskMonitor,
  closeTaskMonitor,
  refreshTaskMonitor,
  killTask,
  openAutomationDashboard,
  closeAutomationDashboard,
  switchAutomationTab,
  saveAutomationSchedule,
  deleteAutomationSchedule,
  executeAutomationSchedule,
};

Object.keys(Actions).forEach((actionName) => {
  if (typeof Actions[actionName] === "function") {
    EventBus.on(actionName, (args) => {
      try {
        console.log("ACTION EXECUTED: " + actionName, args);
        Actions[actionName].apply(null, args);
      } catch (err) {
        console.error(`Error executing action ${actionName}:`, err);
      }
    });
  }
});

if (typeof globalThis.window !== "undefined") {
  globalThis.appVisualViewport = globalThis.visualViewport;
  globalThis.EventBus = EventBus;
  globalThis.sendToTerminal = sendToTerminal;
  globalThis.emitPtyInput = emitPtyInput;
  globalThis.triggerMockTimeouts = () => {
    EventBus.emit("triggerMockTimeouts", []);
  };
  globalThis.mockWakeLockState = { active: false, released: false };
  globalThis.tabs = globalState.tabs;
  globalThis.globalState = globalState;
  globalThis.executeDataAction = executeDataAction;
  // Expose all Actions to globalThis.window for E2E tests
  Object.keys(Actions).forEach((actionName) => {
    globalThis.window[actionName] = Actions[actionName];
  });
}

// CSP Event Delegation
function executeDataAction(code, event) {
  if (!code) return;
  if (code === "document.getElementById('import-settings-input').click()") {
    document.getElementById("import-settings-input").click();
    return;
  }
  if (code === "globalThis.location.href='/test-launcher'") {
    globalThis.location.href = "/test-launcher";
    return;
  }
  if (code.includes("event.stopPropagation();")) {
    event.stopPropagation();
    code = code.replace("event.stopPropagation();", "").trim();
  }
  if (
    code ===
    "globalThis.open(document.getElementById('share-link-input').value, '_blank')"
  ) {
    globalThis.open(
      document.getElementById("share-link-input").value,
      "_blank",
    );
    return;
  }
  if (
    code ===
    "document.getElementById('connection-issue-modal').style.display='none'"
  ) {
    document.getElementById("connection-issue-modal").style.display = "none";
    return;
  }
  if (code === "globalThis.location.reload()") {
    globalThis.location.reload();
    return;
  }
  if (code.startsWith("globalThis.expandedSessionLists")) {
    let m1 = code.match(/expandedSessionLists\.(add|delete)\('([^']+)'\)/);
    if (m1) {
      if (m1[1] === "add") globalThis.expandedSessionLists.add(m1[2]);
      else globalThis.expandedSessionLists.delete(m1[2]);
    }
    let m2 = code.match(
      /fetchSessions\('([^']*)',\s*(\{.*\}),\s*'([^']*)',\s*(true|false),\s*true,\s*true\)/,
    );
    if (m2) {
      let b1 = m2[4] === "true";
      globalThis.fetchSessions(
        m2[1],
        JSON.parse(m2[2].replaceAll("&quot;", '"')),
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
          return s.slice(1, -1).replaceAll("\\'", "'").replaceAll("\\\\", "\\");
        if (s.startsWith('"') && s.endsWith('"'))
          return s
            .slice(1, -1)
            .replaceAll('\\"', '"')
            .replaceAll("\\\\", "\\")
            .replaceAll("&quot;", '"');
        if (!Number.isNaN(s) && s !== "") return Number(s);
        if (s.startsWith("{") || s.startsWith("[")) {
          try {
            return JSON.parse(s.replaceAll("&quot;", '"'));
          } catch (err) {
            console.debug("Ignored error:", err);
          }
        }
        return s;
      });
    }
    if (EventBus.listeners[funcName]) {
      EventBus.emit(funcName, args);
    } else if (typeof globalThis.window[funcName] === "function") {
      globalThis.window[funcName].apply(null, args);
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
    executeDataAction(target.dataset.onclick, e);
  }
});
document.addEventListener("change", function (e) {
  let target = e.target.closest("[data-onchange]");
  if (target) {
    executeDataAction(target.dataset.onchange, e);
  }
});
