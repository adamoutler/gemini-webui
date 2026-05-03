import {
  globalState,
  DEFAULT_PROMPTS,
  getCustomPrompts,
} from "../core/state.js";
import { debugLog } from "../core/api.js"; // NOSONAR
import {
  createTerminalContainer,
  recreateTerminalUI,
  fitTerminal,
} from "../terminal/ui.js";
import { updateStatus, updatePageTitle } from "./launcher.js";
import { renderLauncher } from "../core/session-manager.js"; // NOSONAR
import { fetchSessions } from "../core/session-manager.js"; // NOSONAR
import { fetchWithCSRF } from "../core/api.js"; // NOSONAR
import { sendPromptToTab } from "../../main.js";
import { isMobile } from "../mobile/mobile-input-extra.js";
import { openAddPromptModal, openManagePromptsModal } from "./modals.js";

export async function loadTabsFromServer() {
  // NOSONAR
  try {
    const response = await fetch("/api/sessions/persisted");
    if (!response.ok) throw new Error("Failed to fetch sessions");
    const persisted = await response.json();

    // Clear existing tabs
    globalState.tabs = [];
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
        userNamed: s.user_named || false,
        state: "terminal",
      };
      globalState.tabs.push(tab);
      createTerminalContainer(tid);
      if (tid === globalState.activeTabId) foundActive = true;
    }

    // Always add a launcher if none exist
    if (!globalState.tabs.find((t) => t.state === "launcher")) {
      // NOSONAR
      const id = "tab_" + (Date.now() + Math.floor(Math.random() * 1000));
      globalState.tabs.push({
        id,
        term: null,
        fitAddon: null,
        socket: null,
        session: null,
        title: "+New",
        userNamed: false,
        state: "launcher",
      });
      createTerminalContainer(id);
      renderLauncher(id);
    }
    if (!foundActive) globalState.activeTabId = tabs[0].id;
    renderTabs();
    switchTab(globalState.activeTabId);

    // Start sessions
    globalState.tabs.forEach((t) => {
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
            headers: {
              "Content-Type": "application/json",
            },
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
        // NOSONAR
        localStorage.removeItem("pinned_tabs");
      }
    }
  } catch (e) {
    debugLog("Error loading tabs from server:", e);
    if (globalState.tabs.length === 0) addNewTab();
  }
}
export function syncTabs(serverTabs) {
  debugLog("Syncing tabs from server:", serverTabs);
  let changed = false;

  // Remove tabs no longer on server
  for (let i = globalState.tabs.length - 1; i >= 0; i--) {
    const t = globalState.tabs[i];
    if (t.state === "terminal" && !serverTabs[t.id]) {
      closeTab(t.id, null, true);
      changed = true;
    }
  }

  // Add or update tabs
  for (const tid in serverTabs) {
    const s = serverTabs[tid];
    const existing = globalState.tabs.find((t) => t.id === tid);
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
      globalState.tabs.push(tab);
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
export function saveTabsToStorage() {
  sessionStorage.setItem("gemini_active_tab", globalState.activeTabId);
}
export function loadTabsFromStorage() {
  loadTabsFromServer();
  return true;
}
export async function addNewTab(autoResume = false) {
  // If a launcher tab already exists, just switch to it instead of creating a new one.
  const existingLauncher = globalState.tabs.find((t) => t.state === "launcher");
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
    title: "+New",
    userNamed: false,
    state: "launcher",
  };
  const container = document.createElement("div");
  container.id = id + "_instance";
  container.className = "tab-instance";
  document.getElementById("terminal-container").appendChild(container);
  globalState.tabs.push(tab);
  renderTabs();
  switchTab(id);
  renderLauncher(id);
  saveTabsToStorage();
}
export function switchTab(id) {
  // NOSONAR
  globalState.activeTabId = id;
  globalThis.globalState.activeTabId = id;
  const tab = globalState.tabs.find((t) => t.id === id);
  if (!tab) return;
  if (launcherRefreshInterval) {
    clearInterval(launcherRefreshInterval);
    launcherRefreshInterval = null; // NOSONAR
  }
  if (tab.state === "launcher") {
    // Trigger a refresh and restart polling when switching back to launcher
    // We don't re-render the whole launcher, just the dynamic parts if they exist
    const container = document.getElementById(id + "_instance");
    if (container && container.querySelector(".launcher")) {
      // NOSONAR
      fetch("/api/hosts")
        .then((r) => r.json())
        .then((hosts) => {
          hosts.forEach((conn, index) => {
            const sessionListId = `${id}_sessions_${conn.label.replace(
              // NOSONAR
              /[^a-z0-9]/gi,
              "",
            )}`;
            setTimeout(() => {
              fetchSessions(id, conn, sessionListId, false, false);
            }, index * 500);
          });
          if (launcherRefreshInterval) clearInterval(launcherRefreshInterval);
        });
    } else {
      // If the launcher was not fully rendered (e.g. previous fetch failed), render it now.
      renderLauncher(id);
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
      globalState.tabs.forEach((t) => {
        if (t.mobileProxy && t.mobileProxy.ui && t.term) {
          // NOSONAR
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
export function restartActiveTab() {
  const tab = globalState.tabs.find((t) => t.id === globalState.activeTabId);
  if (tab && tab.state === "terminal") {
    // NOSONAR
    const { ssh_target, ssh_dir, resume } = tab.session;
    tab.term.clear();
    fitTerminal(tab);
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
export function closeTab(id, event, isLocalOnly = false) {
  // NOSONAR
  if (event) event.stopPropagation();
  const index = globalState.tabs.findIndex((t) => t.id === id);
  if (index === -1) return;
  const tab = globalState.tabs[index];
  if (tab.state === "launcher") return; // Cannot close the launcher (+ New) tab

  if (!isLocalOnly) {
    if (!confirm("Are you sure you want to terminate this session?")) {
      return;
    }
    // 1. Emit targeted WebSocket termination event
    if (tab.socket && tab.socket.connected) {
      // NOSONAR
      debugLog("Emitting terminate_session via WebSocket for tab: " + id);
      tab.socket.emit("terminate_session", {
        tab_id: id,
      });
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
    } catch (e) {} // NOSONAR
  }
  if (tab.term) tab.term.dispose();
  const inst = document.getElementById(id + "_instance");
  if (inst) inst.remove();
  globalState.tabs.splice(index, 1);
  if (globalState.tabs.length === 0) addNewTab();
  else {
    if (globalState.activeTabId === id)
      switchTab(globalState.tabs[Math.max(0, index - 1)].id);
    renderTabs();
  }
  saveTabsToStorage();
  updatePageTitle();
}
export function renderTabs() {
  const bar = document.getElementById("tab-bar");
  bar.innerHTML = "";
  globalState.tabs.forEach((tab) => {
    const el = document.createElement("div");
    el.id = "nav-" + tab.id;
    el.className =
      "tab" + (tab.id === globalState.activeTabId ? " active" : "");
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
      `<span>${tab.title || "\u00A0"}</span>` +
      (tab.state === "launcher"
        ? ""
        : `<span class="tab-close" data-onclick="closeTab('${tab.id}', event, false)">&times;</span>`);
    bar.appendChild(el);
  });
}
export function showTabContextMenu(id, x, y) {
  // Remove existing menu if any
  const existingMenu = document.getElementById("tab-context-menu");
  if (existingMenu) existingMenu.remove();
  const menu = document.createElement("div");
  menu.id = "tab-context-menu";
  menu.className = "context-menu js-style-87d2f1"; // Shared style for menus
  menu.style.left = x + "px";
  menu.style.top = y + "px";
  const tab = globalState.tabs.find((t) => t.id === id);
  if (!tab) {
    return;
  }
  const sections = [
    {
      title: "Tab Actions",
      items: [
        {
          label: "New Tab",
          action: () => addNewTab(),
        },
        {
          label: "Rename Tab",
          action: () => {
            const newTitle = prompt("Enter new tab title:", tab.title);
            if (newTitle) {
              tab.title = newTitle;
              tab.userNamed = true;
              if (tab.socket) {
                tab.socket.emit("update_title", {
                  tab_id: tab.id,
                  title: newTitle,
                  user_named: true,
                });
              }
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
        {
          label: "Add Prompt",
          action: () => openAddPromptModal(),
        },
        {
          label: "Manage Prompts",
          action: () => openManagePromptsModal(),
        },
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

globalThis.loadTabsFromServer = loadTabsFromServer;
globalThis.syncTabs = syncTabs;
globalThis.loadTabsFromStorage = loadTabsFromStorage;
globalThis.addNewTab = addNewTab;
globalThis.showTabContextMenu = showTabContextMenu;
globalThis.renderTabs = renderTabs;
globalThis.switchTab = switchTab;
globalThis.closeTab = closeTab;
globalThis.restartActiveTab = restartActiveTab;
globalThis.saveTabsToStorage = saveTabsToStorage;
