import { globalState } from "../core/state.js";
import { debugLog } from "../core/api.js";

export function createTerminalContainer(id) {
  if (document.getElementById(id + "_instance")) return;
  const container = document.createElement("div");
  container.id = id + "_instance";
  container.className = "tab-instance";
  document.getElementById("terminal-container").appendChild(container);
}

export function recreateTerminalUI(tab, shouldReclaim = false) {
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

export function startSession(
  tabId,
  type,
  target,
  dir,
  resumeParam = true,
  sessionName = null,
  shouldReclaim = false,
) {
  const tab = globalState.tabs.find((t) => t.id === tabId);
  if (!tab) {
    return;
  }

  if (resumeParam === false || String(resumeParam) === "new") {
    // WARNING: Do NOT attempt to "predict" the session ID here (e.g. maxId + 1).
    // The gemini backend expects "new" to spawn a new session (-n flag).
    // If we pass an invalid predicted ID (like 58), the CLI will return "Invalid session identifier"
    // and refuse to start cleanly. The actual session ID is captured later from the
    // "Session established. ID: X" output from the terminal.
    resumeParam = "new";
  }

  if (target === "null" || target === "undefined") target = "";
  if (dir === "null" || dir === "undefined") dir = "";

  tab.state = "terminal";
  tab.session = { type, ssh_target: target, ssh_dir: dir, resume: resumeParam };
  tab.shouldReclaim = shouldReclaim;

  // Back button hijacking: push state so "back" has something to pop
  globalThis.history.pushState({ terminal: true, tabId: tabId }, "");
  globalThis.saveTabsToStorage();
  globalThis.renderTabs();

  const container = document.getElementById(tabId + "_instance");
  container.innerHTML = "";

  const termDiv = document.createElement("div");
  termDiv.className = "terminal-instance";
  termDiv.id = "rolling-log-" + tabId;
  termDiv.setAttribute("role", "log");
  termDiv.setAttribute("aria-live", "polite");
  termDiv.setAttribute("aria-relevant", "additions");
  container.appendChild(termDiv);

  globalThis.switchTab(tabId);

  if (!document.documentElement.classList.contains("is-mobile")) {
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
          if (x + rect.width > globalThis.innerWidth) {
            desktopContextMenu.style.left =
              globalThis.innerWidth - rect.width - 5 + "px";
          }
          if (y + rect.height > globalThis.innerHeight) {
            desktopContextMenu.style.top =
              globalThis.innerHeight - rect.height - 5 + "px";
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
    fontSize: globalState.currentFontSize,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    allowProposedApi: true,
    theme: globalThis.terminalTheme,
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
  fitTerminal(tab);

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
        if (tab.term) {
          tab.term.refresh(0, tab.term.rows - 1);
        }
      });
    } else if (typeof WebglAddon !== "undefined") {
      debugLog("WebGL addon explicitly disabled or test environment detected");
    }
  } catch (e) {
    debugLog("WebGL addon could not be loaded", e);
  }

  // Passive Portal Implementation for Native Momentum
  if (document.documentElement.classList.contains("is-mobile")) {
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

        // If the browser resets scrollTop abruptly (e.g., backgrounding PWA), recenter without scrolling
        if (Math.abs(deltaScroll) > 10000) {
          isSyncing = true;
          proxy.scrollTop = 50000;
          lastScrollTop = 50000;
          selectionOverlay.style.top = proxy.scrollTop + "px";
          setTimeout(() => {
            isSyncing = false;
          }, 10);
          return;
        }

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
          const style = globalThis.getComputedStyle(termRows);
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
          globalThis.getSelection().removeAllRanges();

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
      const selection = globalThis.getSelection().toString();
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
        for (const match of fullText.matchAll(urlRegex)) {
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
                globalThis.open(uri, "_blank", "noopener,noreferrer");
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
      const items = (e.clipboardData || globalThis.clipboardData)?.items;
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

  tab.socket = io.connect(globalThis.location.origin, {
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
    console.log("handleConnect called for tab " + tabId);
    disconnectTime = null;
    if (tab.term) {
      tab.term.clear();
    }
    tab.term.write("\r\n\x1b[2m[Connected to server]\x1b[0m\r\n");
    console.log("Calling globalThis.updateStatus for tab " + tabId);
    globalThis.updateStatus(tab.session.ssh_target, tab.session.ssh_dir); // Restore correct status

    // Refresh CSRF token on reconnect in case server restarted
    try {
      await refreshCsrfToken();
    } catch (e) {
      console.error("Failed to refresh CSRF token:", e);
    }

    // Fit terminal to window immediately before telling backend the size
    fitTerminal(tab);

    tab.socket.emit("join_room", { tab_id: tabId });
    if (tab.shouldReclaim) {
      tab.term.clear();
    }
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
      tab.socket.disconnect();
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

  tab.socket.on("session-terminated", () => {
    debugLog("Session terminated via tab socket:", tabId);
    globalThis.closeTab(tabId, null, true);
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
        fitTerminal(tab);
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
      if (data.output.includes("Resume failed, starting new session...")) {
        console.log("Detected resume failure, clearing geminiResume");
        localStorage.removeItem("geminiResume");
        if (tab.session) {
          tab.session.resume = "new";
          if (typeof globalThis.saveTabsToStorage === "function")
            globalThis.saveTabsToStorage();
        }
      }
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
      if (globalThis.emitPtyInput) globalThis.emitPtyInput(tab, data);
      else emitPtyInput(tab, data);
    }
  });
  tab.term.onTitleChange((title) => {
    if (!tab.userNamed) {
      tab.title = title;
      if (tab.socket) {
        tab.socket.emit("update_title", { tab_id: tab.id, title: title });
      }
      globalThis.renderTabs();
      updatePageTitle();
    }

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
      if (document.documentElement.classList.contains("is-mobile"))
        return false;
    }
    if (e.type === "keydown" && e.key === "Backspace") {
      if (document.documentElement.classList.contains("is-mobile"))
        return false;
    }

    return true;
  });
  globalThis.renderTabs();
  globalThis.switchTab(tabId);
}

export function fitTerminal(tab) {
  if (!tab || tab.state !== "terminal" || !tab.term || !tab.fitAddon) return;
  const oldCols = tab.term.cols;
  const oldRows = tab.term.rows;
  try {
    requestAnimationFrame(() => {
      try {
        tab.fitAddon.fit();
        if (tab.term.cols !== oldCols || tab.term.rows !== oldRows) {
          if (tab.socket && tab.socket.connected) {
            tab.socket.emit("resize", {
              cols: tab.term.cols,
              rows: tab.term.rows,
            });
          }
        }
      } catch (e) {}
    });
  } catch (e) {
    // Silently ignore fit errors during initialization (e.g. xterm-addon-fit dimensions getter throws)
  }
}
