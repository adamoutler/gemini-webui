import { globalState } from "../core/state.js";

let desktopContextMenuInitialized = false;
let menuElement = null;

export function initDesktopContextMenu() {
  if (
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
      navigator.userAgent,
    )
  )
    return;

  if (!desktopContextMenuInitialized) {
    desktopContextMenuInitialized = true;
    menuElement = document.createElement("div");
    menuElement.id = "desktop-context-menu";
    menuElement.className = "desktop-context-menu";
    menuElement.innerHTML = `
      <div class="menu-item" id="ctx-copy">Copy</div>
      <div class="menu-item" id="ctx-paste">Paste</div>
    `;
    document.body.appendChild(menuElement);

    menuElement
      .querySelector("#ctx-copy")
      .addEventListener("mousedown", (e) => {
        e.preventDefault();
        const tab = globalState.tabs.find(
          (t) => t.id === globalState.activeTabId,
        );
        if (tab?.term && tab.term.hasSelection()) {
          const selectedText = tab.term.getSelection();
          navigator.clipboard.writeText(
            globalThis.filterTerminalFluff
              ? globalThis.filterTerminalFluff(selectedText)
              : selectedText,
          );
        } else {
          document.execCommand("copy");
        }
        menuElement.style.display = "none";
      });

    menuElement
      .querySelector("#ctx-paste")
      .addEventListener("mousedown", async (e) => {
        e.preventDefault();
        try {
          let text = await navigator.clipboard.readText();
          const tab = globalState.tabs.find(
            (t) => t.id === globalState.activeTabId,
          );
          if (tab?.socket) {
            const useBracketedPaste =
              tab.term && tab.term.modes && tab.term.modes.bracketedPasteMode;
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
        menuElement.style.display = "none";
      });

    document.addEventListener("mousedown", (e) => {
      if (
        menuElement.style.display === "block" &&
        !e.target.closest("#desktop-context-menu")
      ) {
        menuElement.style.display = "none";
      }
    });

    // Global document contextmenu handling for non-terminal areas
    document.addEventListener("contextmenu", (e) => {
      if (document.documentElement.classList.contains("is-mobile")) return;

      const isTextSelected = globalThis.getSelection().toString().length > 0;
      const isInput =
        e.target.tagName === "INPUT" ||
        e.target.tagName === "TEXTAREA" ||
        e.target.isContentEditable;
      if (isTextSelected || isInput) return;

      let el = e.target;
      let allowMenu = false;
      while (el) {
        if (el.classList && el.classList.contains("xterm-cursor-layer")) {
          allowMenu = true;
          break;
        }
        if (
          el.id === "terminal-container" ||
          el.id === "tabs-container" ||
          el.tagName === "A" ||
          el.tagName === "BUTTON"
        ) {
          allowMenu = true;
          break;
        }
        el = el.parentElement;
      }

      // If right-clicked on terminal container or body, show custom menu
      if (
        allowMenu ||
        el === document.body ||
        el === document.documentElement
      ) {
        e.preventDefault();
        showDesktopContextMenu(e.pageX, e.pageY);
      } else {
        e.preventDefault();
      }
    });
  }
}

export function showDesktopContextMenu(x, y) {
  if (menuElement) {
    menuElement.style.left = `${x}px`;
    menuElement.style.top = `${y}px`;
    menuElement.style.display = "block";
  }
}
