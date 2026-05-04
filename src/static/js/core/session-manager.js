import { debugLog, escapeHtml, customFetch } from "./api.js";
import { getGlobalSocket } from "./socket.js";
import { HostStateManager } from "../ui/launcher.js";
import { EventBus } from "./event-bus.js";
import { globalState } from "./state.js";

export let backendSessionLastSeen = {};
export let backendSessionStatusClass = {};
export function refreshBackendSessionsList(id) {
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
            const _reflow = statusNode.offsetWidth;
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
export async function renderLauncher(id) {
  const container = document.getElementById(id + "_instance");
  if (!container || container.dataset.rendering === "true") return;
  container.dataset.rendering = "true";
  try {
    const config = await (await fetch("/api/config")).json();
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
    let bulkCache = null;
    try {
      const socket = getGlobalSocket();
      bulkCache = await new Promise((resolve) => {
        const timeoutTimer = setTimeout(() => resolve(null), 5000);
        socket.emit("get_all_sessions", {}, (response) => {
          clearTimeout(timeoutTimer);
          if (response && response.status === "success") {
            resolve(response.cache);
          } else {
            resolve(null);
          }
        });
      });
    } catch (e) {
      console.error("Failed to fetch bulk sessions cache", e);
    }

    // Set up polling while this launcher is visible
    const connContainer = document.getElementById(id + "_connections");
    if (!connContainer) return;
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
                                <span class="js-style-037e58" title="${
                                  conn.label
                                }">${conn.label}</span>
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
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(newLabels),
        });
      });
      let dragOffset = {
        x: 0,
        y: 0,
      };

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
        {
          passive: false,
        },
      );
      handle.addEventListener(
        "touchmove",
        (e) => {
          e.preventDefault();
          if (!draggedCard) return;
          const touch = e.touches[0];
          draggedCard.style.left = touch.clientX - dragOffset.x + "px";
          draggedCard.style.top = touch.clientY - dragOffset.y + "px";
          const target = document.elementFromPoint(
            touch.clientX,
            touch.clientY,
          );
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
        {
          passive: false,
        },
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
          headers: {
            "Content-Type": "application/json",
          },
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
      const cacheKey = `${conn.type === "ssh" ? "ssh" : "local"}:${
        conn.target || "local"
      }:${conn.dir || ""}`;
      const preloadedData =
        bulkCache && bulkCache[cacheKey] ? bulkCache[cacheKey] : null;
      if (preloadedData) {
        fetchSessions(
          id,
          conn,
          sessionListId,
          false,
          true,
          false,
          preloadedData,
        );
      } else {
        setTimeout(() => {
          fetchSessions(id, conn, sessionListId, false, true); // Use cache first
        }, index * 500);
      }
    });
  } finally {
    delete container.dataset.rendering;
  }
}
export async function terminateBackendSession(launcherTabId, tabId) {
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
      if (contentType && contentType.includes("application/json")) {
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
export async function terminateAllBackendSessions(launcherTabId) {
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
      if (contentType && contentType.includes("application/json")) {
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
export function reclaimBackendSession(id, tabId, title, session) {
  const tab = globalState.tabs.find((t) => t.id === id);
  if (!tab) return;

  // Update DOM ID to match new tab ID
  const container = document.getElementById(id + "_instance");
  if (container) container.id = tabId + "_instance";
  if (globalState.globalState.activeTabId === id)
    globalState.activeTabId = tabId;
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
  EventBus.emit("renderTabs", []);
  EventBus.emit("saveTabsToStorage", []);
  EventBus.emit("recreateTerminalUI", [tab, true]);
}

export let consecutiveTimeouts = {};
export async function fetchSessions(
  tabId,
  conn,
  targetId,
  forceAll = false,
  useCache = false,
  isPolling = false,
  preloadedData = null,
) {
  debugLog(
    "FETCH SESSIONS CALLED WITH useCache=" +
      useCache +
      " isPolling=" +
      isPolling,
  );
  if (!globalThis.expandedSessionLists)
    globalThis.expandedSessionLists = new Set();
  if (globalThis.expandedSessionLists.has(conn.label)) {
    forceAll = true;
  }
  let data;
  try {
    if (preloadedData) {
      data = preloadedData;
    } else {
      const params = {};
      if (conn.type === "ssh") {
        params.ssh_target = conn.target;
        if (conn.dir) params.ssh_dir = conn.dir;
      }
      if (useCache) params.cache = true;
      params.bg = true;
      debugLog("FETCH SESSIONS START");
      data = await new Promise((resolve, reject) => {
        const socket = getGlobalSocket();
        const timeoutTimer = setTimeout(() => {
          resolve({
            error: "Timeout waiting for get_sessions",
          });
        }, 5000);
        socket.emit("get_sessions", params, (response) => {
          clearTimeout(timeoutTimer);
          if (
            response &&
            response.error &&
            !response.output &&
            !response.sessions
          ) {
            console.log("GET_SESSIONS_RESPONSE:", response);
            resolve(response); // Handle errors explicitly like API did
          } else if (response) {
            console.log("GET_SESSIONS_RESPONSE:", response);
            resolve(response);
          } else {
            reject(new Error("No response from WebSocket"));
          }
        });
      });
    }
    debugLog("FETCH SESSIONS DATA: ", JSON.stringify(data));
    if (data.error === "Fetch in progress") {
      data.status = "fetching";
      data.error = null;
    }
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
        HostStateManager.updateHealth(tabId, conn.label, !data.error, false);
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
        debugLog("Multiple timeouts detected");
        consecutiveTimeouts[timeoutKey] = 0;
        listEl.innerHTML = `<div class="js-style-7b7303">Connection unstable. Please refresh manually if needed.</div>`;
        return;
      }
      if (!useCache || isPolling) {
        try {
          HostStateManager.updateHealth(tabId, conn.label, false, false);
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
    console.log(
      "SESSIONS: ",
      sessions.map((s) => s.uuid),
    );
    const activeTerminalTab = globalState.tabs.find(
      (t) =>
        t.state === "terminal" &&
        t.session &&
        (t.session.ssh_target || "") === (conn.target || "") &&
        (t.session.ssh_dir || "") === (conn.dir || ""),
    );
    console.log(
      "TABS: ",
      JSON.stringify(globalState.tabs),
      "CONN:",
      JSON.stringify(conn),
    );
    console.log("ACTIVE TAB:", activeTerminalTab);
    if (
      activeTerminalTab &&
      activeTerminalTab.session.resume &&
      (activeTerminalTab.session.resume === "new" ||
        /^\d+$/.test(activeTerminalTab.session.resume))
    ) {
      const match = sessions.find(
        (s) =>
          s.id === activeTerminalTab.session.resume ||
          s.uuid === activeTerminalTab.id,
      );
      if (match && match.uuid) {
        activeTerminalTab.session.resume = match.uuid;
        const socket = getGlobalSocket();
        if (socket && socket.connected) {
          socket.emit("update_resume", {
            tab_id: activeTerminalTab.id,
            resume: match.uuid,
          });
        }
        EventBus.emit("saveTabsToStorage", []);
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
        }', '${escapeHtml(
          String(s.name).replace(/\\/g, "\\\\").replace(/'/g, "\\'"),
        )}', false)">
                    <div class="session-name">${escapeHtml(s.name)}</div>
                    <div class="session-meta">ID #${escapeHtml(
                      String(s.id),
                    )} • ${escapeHtml(String(s.meta))}</div>
                 </div>`;
      });
      if (!forceAll && sorted.length > 3) {
        html += `<div class="session-item js-style-86c2b8" data-onclick="globalThis.expandedSessionLists.add('${escapeHtml(
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
        html += `<div class="session-item js-style-86c2b8" data-onclick="globalThis.expandedSessionLists.delete('${escapeHtml(
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
      HostStateManager.updateHealth(tabId, conn.label, false, false);
    }
    console.error(e);
  }
}
export function parseSessions(output) {
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

export function reclaimStolenSession() {
  const tab = globalState.tabs.find((t) => t.id === globalState.activeTabId);
  if (tab && tab.stolen) {
    tab.stolen = false;
    const reclaimBtn = document.getElementById("reclaim-btn");
    if (reclaimBtn) reclaimBtn.style.display = "none";
    if (tab.socket) {
      tab.socket.connect();
      EventBus.emit("updateStatus", [
        tab.session.ssh_target,
        tab.session.ssh_dir,
      ]);
    }
  }
}
