import { EventBus } from "../core/event-bus.js"; // NOSONAR

export const checkMobile = () => {
  // Strictly target Android as requested
  const isAndroid = /Android/i.test(navigator.userAgent);
  const isTouch = "ontouchstart" in window || navigator.maxTouchPoints > 0; // NOSONAR

  // Increase width threshold to 1024px to support Android tablets (Nexus 9/Pixel Tablet)
  const isNarrow = globalThis.innerWidth <= 1024;

  // Explicitly exclude Apple devices
  const isApple = /iPhone|iPad|iPod|Macintosh/i.test(navigator.userAgent);

  // Return true if explicitly Android, or a narrow touch device that is not Apple
  return isAndroid || (isNarrow && isTouch && !isApple);
};
export const isMobile = checkMobile();
if (isMobile) {
  document.documentElement.classList.add("is-mobile");
}
debugLog(
  "Environment detection: isMobile =",
  isMobile,
  "(UA:",
  navigator.userAgent,
  "Width:",
  globalThis.innerWidth,
  "Touch:",
  "ontouchstart" in window || navigator.maxTouchPoints > 0, // NOSONAR
  ")",
);

// VisualViewport logic is handled at the bottom of the script

globalThis.addEventListener("popstate", (event) => {
  const activeTab = tabs.find((t) => t.id === activeTabId);
  // Only hijack if we are currently in a terminal.
  // If we are already in launcher mode, let the back button work normally.
  if (activeTab && activeTab.state === "terminal") {
    // NOSONAR
    addNewTab();
  }
});

import { globalState } from "../core/state.js";
import { fitTerminal } from "../terminal/ui.js";

export let resizeObserverTimeout; // NOSONAR
const resizeObserver = new ResizeObserver(() => {
  clearTimeout(resizeObserverTimeout);
  resizeObserverTimeout = setTimeout(() => {
    globalState.tabs.forEach((tab) => fitTerminal(tab));
  }, 50);
});
resizeObserver.observe(document.getElementById("terminal-container"));

// Abstract visualViewport so it can be mocked in tests
globalThis.appVisualViewport = globalThis.visualViewport
  ? {
      get height() {
        return globalThis.visualViewport.height;
      },
      get scale() {
        return globalThis.visualViewport.scale;
      },
      get offsetTop() {
        return globalThis.visualViewport.offsetTop;
      },
      get offsetLeft() {
        return globalThis.visualViewport.offsetLeft;
      },
      addEventListener: globalThis.visualViewport.addEventListener.bind(
        globalThis.visualViewport,
      ),
      removeEventListener: globalThis.visualViewport.removeEventListener.bind(
        globalThis.visualViewport,
      ),
    }
  : null;

// Handle mobile keyboard resizing using Visual Viewport API
if (globalThis.appVisualViewport) {
  let resizeTimeout;
  let lastViewHeight = globalThis.appVisualViewport.height;
  const updateViewport = () => {
    if (globalThis.appVisualViewport.scale > 1.05) {
      return; // User is zooming, do not break layout
    }
    const viewHeight = globalThis.appVisualViewport.height;
    const offsetTop = globalThis.appVisualViewport.offsetTop || 0;

    // Use a CSS variable for height for smoother rendering across components
    document.documentElement.style.setProperty("--vh", `${viewHeight}px`);

    // Lock body to the visible viewport height to prevent scrolling past keyboard
    document.body.style.height = `${viewHeight}px`;

    // On iOS Safari, the visual viewport moves independently of the layout viewport.
    // We counteract this by positioning the body exactly where the visual viewport is.
    if (Math.abs(offsetTop) > 0.1) {
      document.body.style.top = `${offsetTop}px`;
      // Prevent browser from trying to scroll the layout viewport
      if (globalThis.scrollY !== 0) {
        globalThis.scrollTo(0, 0);
      }
    } else {
      document.body.style.top = "0";
    }
  };
  globalThis.appVisualViewport.addEventListener("resize", () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      if (globalThis.appVisualViewport.scale > 1.05) {
        return; // User is zooming, do not break layout
      }
      const viewHeight = globalThis.appVisualViewport.height;
      // Ignore tiny jitters (less than 10px) to prevent scroll interruption
      if (Math.abs(viewHeight - lastViewHeight) < 10) return;
      lastViewHeight = viewHeight;
      updateViewport();
      tabs.forEach((tab) => {
        fitTerminal(tab);
        // Immediate alignment of proxy input after xterm resizes
        if (tab.mobileProxy && tab.mobileProxy.ui && tab.term) {
          // NOSONAR
          tab.mobileProxy.ui.alignWithCursor(tab.term);
        }
      });
    }, 60); // Faster response time for snappier keyboard feel
  });
  globalThis.appVisualViewport.addEventListener("scroll", updateViewport);

  // Also initialize with the current height
  updateViewport();
}
setTimeout(() => {
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
    activeTabId = id; // NOSONAR
    renderTabs();
    startSession(id, "local", "", "", sessionId, "Test Session", true);
    if (!document.getElementById("friction-modal")) {
      const modalHtml = `
                  <div class="friction-modal js-style-224b51" id="friction-modal">
                      <div class="friction-modal-content">
                          <h2>Session Disconnected</h2>
                          <p>The test session has ended or disconnected.</p>
                          <div class="friction-actions">
                              <button class="primary" data-onclick="globalThis.location.href='/test-launcher'">Start Fresh Test</button>
                              <button class="danger" data-onclick="forceReconnect()">Force Reconnect</button>
                          </div>
                      </div>
                  </div>
              `;
      document.body.insertAdjacentHTML("beforeend", modalHtml);
    }
    globalThis.forceReconnect = () => {
      document.getElementById("friction-modal").style.display = "none";
      const currentTab = tabs.find((t) => t.id === activeTabId);
      if (currentTab && currentTab.socket) {
        // NOSONAR
        currentTab.socket.connect();
      }
    };
    globalThis.addEventListener("beforeunload", (e) => {
      document.getElementById("friction-modal").style.display = "flex";
      e.preventDefault();
      e.returnValue = ""; // NOSONAR
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
}, 0);

// --- Quick Connect Logic ---

export const mobileControlsContainer =
  document.getElementById("mobile-controls");
if (mobileControlsContainer) {
  mobileControlsContainer.addEventListener(
    "touchmove",
    (e) => {
      e.preventDefault();
    },
    {
      passive: false,
    },
  );
}

// Setup Hold-to-Repeat for mobile buttons
document.querySelectorAll(".control-btn.holdable").forEach((btn) => {
  let timeoutId = null;
  let intervalId = null;
  let isActive = false;
  const executeAction = (e) => {
    let cmd = btn.dataset.cmd;
    const adjust = btn.dataset.funcAdjust;
    if (cmd) {
      // Unescape characters like \x1b and \t from the DOM attribute string
      cmd = cmd.replace(
        /\\x([0-9A-Fa-f]{2})/g,
        (
          match,
          hex, // NOSONAR
        ) => String.fromCodePoint(Number.parseInt(hex, 16)),
      );
      cmd = cmd.replace(/\\t/g, "\t"); // NOSONAR
      cmd = cmd.replace(/\\r/g, "\r"); // NOSONAR
      cmd = cmd.replace(/\\n/g, "\n"); // NOSONAR

      // Handle Shift modifier toggle from MobileModifierState for Tab key
      const isShift =
        (e && e.shiftKey) || // NOSONAR
        (typeof MobileModifierState !== "undefined" &&
          MobileModifierState.instance && // NOSONAR
          MobileModifierState.instance.shiftActive);
      if (cmd === "\t" && isShift) {
        cmd = "\x1b[Z";
        if (
          MobileModifierState.instance && // NOSONAR
          MobileModifierState.instance.shiftActive
        ) {
          MobileModifierState.instance.toggleShift(false);
        }
      }
      globalThis.sendToTerminal(cmd);
    }
    if (adjust) {
      adjustFontSize(Number.parseInt(adjust));
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
    if (e && e.type === "touchend") e.preventDefault(); // NOSONAR
    isActive = false;
    btn.style.opacity = "1";
    clearTimeout(timeoutId);
    clearInterval(intervalId);
  };
  btn.addEventListener("mousedown", startAction);
  btn.addEventListener("touchstart", startAction, {
    passive: false,
  });
  btn.addEventListener("mouseup", stopAction);
  btn.addEventListener("mouseleave", stopAction);
  btn.addEventListener("touchend", stopAction);
  btn.addEventListener("touchcancel", stopAction);
});
export const wsDownloadInput = document.getElementById(
  "workspace-download-filename",
);
export const autocompleteResults = document.getElementById(
  "autocomplete-results",
);
let downloadDebounceTimer;
wsDownloadInput.addEventListener("input", () => {
  clearTimeout(downloadDebounceTimer);
  autocompleteResults.style.display = "none";
  downloadDebounceTimer = setTimeout(async () => {
    const q = wsDownloadInput.value;
    const tab = tabs.find((t) => t.id === activeTabId);
    if (!tab || tab.session.type !== "ssh" || !q) {
      // NOSONAR
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
// --- Drag and Drop Feature ---
const dropZone = document.createElement("div");
dropZone.className = "drop-zone";
dropZone.innerText = "Drop files here to upload";
document.body.appendChild(dropZone);
document.addEventListener("dragover", (e) => {
  const activeTab = tabs.find((t) => t.id === activeTabId);
  if (!activeTab || activeTab.state !== "terminal") return; // NOSONAR
  e.preventDefault();
  dropZone.classList.add("active");
});
document.addEventListener("dragleave", (e) => {
  const activeTab = tabs.find((t) => t.id === activeTabId);
  if (!activeTab || activeTab.state !== "terminal") return; // NOSONAR
  e.preventDefault();
  if (e.target === dropZone || e.relatedTarget === null) {
    dropZone.classList.remove("active");
  }
});
document.addEventListener("drop", async (e) => {
  // NOSONAR
  const activeTab = tabs.find((t) => t.id === activeTabId);
  if (!activeTab || activeTab.state !== "terminal") return; // NOSONAR
  e.preventDefault();
  dropZone.classList.remove("active");
  async function traverseFileTree(item, path = "") {
    // NOSONAR
    return new Promise((resolve) => {
      if (item.isFile) {
        item.file((file) => {
          resolve([
            {
              file,
              path: path + file.name,
            },
          ]);
        });
      } else if (item.isDirectory) {
        const dirReader = item.createReader();
        dirReader.readEntries(async (entries) => {
          let files = [];
          for (let i = 0; i < entries.length; i++) {
            // NOSONAR
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
      // NOSONAR
      const item = e.dataTransfer.items[i].webkitGetAsEntry();
      if (item) {
        promises.push(traverseFileTree(item));
      }
    }
    const results = await Promise.all(promises);
    allFiles = results.flat();
  } else if (e.dataTransfer.files) {
    for (let i = 0; i < e.dataTransfer.files.length; i++) {
      // NOSONAR
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
        // NOSONAR
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
        // NOSONAR
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
  // NOSONAR
  if (e.key === "Escape") {
    const fileTransferModal = document.getElementById("file-transfer-modal");
    const dropZone = document.querySelector(".drop-zone");
    if (
      (fileTransferModal && fileTransferModal.style.display === "block") || // NOSONAR
      (dropZone && dropZone.classList.contains("active")) // NOSONAR
    ) {
      if (fileTransferModal) closeFileTransfer();
      if (dropZone) dropZone.classList.remove("active");
      return;
    }
    const settingsModal = document.getElementById("settings-modal");
    if (settingsModal && settingsModal.style.display === "block") {
      // NOSONAR
      closeSettings();
      return;
    }
    const activeTab = tabs.find((t) => t.id === activeTabId);
    if (activeTab && activeTab.state === "launcher" && tabs.length > 1) {
      // NOSONAR
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
export let desktopContextMenuInitialized = false; // NOSONAR
export function initDesktopContextMenu() {
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
      // NOSONAR
      const selectedText = tab.term.getSelection();
      navigator.clipboard.writeText(filterTerminalFluff(selectedText));
    } else {
      document.execCommand("copy"); // NOSONAR
    }
    menu.style.display = "none";
  });
  menu.querySelector("#ctx-paste").addEventListener("mousedown", async (e) => {
    e.preventDefault();
    try {
      let text = await navigator.clipboard.readText();
      const tab = tabs.find((t) => t.id === activeTabId);
      if (tab && tab.socket) {
        // NOSONAR
        const useBracketedPaste =
          tab.term && tab.term.modes && tab.term.modes.bracketedPasteMode; // NOSONAR
        if (useBracketedPaste) {
          text = "\x1b[200~" + text + "\x1b[201~";
        }
        if (globalThis.emitPtyInput) {
          globalThis.emitPtyInput(tab, text);
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
    globalThis.matchMedia("(display-mode: standalone)").matches ||
    globalThis.navigator.standalone ||
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

export function triggerHapticFeedback() {
  if (navigator.vibrate) {
    navigator.vibrate(5);
  }
}
