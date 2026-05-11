import { TerminalModule } from "../pipeline/TerminalModule.js";

export class ContextMenuPlugin extends TerminalModule {
  constructor() {
    super("ContextMenuPlugin", 70);
    this.menuElement = null;
  }

  setup(terminal, tab) {
    this.terminal = terminal;
    this.tab = tab;

    if (document.getElementById("desktop-context-menu")) {
      this.menuElement = document.getElementById("desktop-context-menu");
    } else {
      this.menuElement = document.createElement("div");
      this.menuElement.id = "desktop-context-menu";
      this.menuElement.className = "desktop-context-menu";
      this.menuElement.innerHTML = `
        <div class="menu-item" id="ctx-copy">Copy</div>
        <div class="menu-item" id="ctx-paste">Paste</div>
      `;
      document.body.appendChild(this.menuElement);

      this.menuElement
        .querySelector("#ctx-copy")
        .addEventListener("mousedown", (e) => {
          e.preventDefault();
          const selectedText = this.terminal.getSelection();
          if (selectedText) {
            navigator.clipboard.writeText(
              globalThis.filterTerminalFluff
                ? globalThis.filterTerminalFluff(selectedText)
                : selectedText,
            );
          } else {
            document.execCommand("copy");
          }
          this.menuElement.style.display = "none";
        });

      this.menuElement
        .querySelector("#ctx-paste")
        .addEventListener("mousedown", async (e) => {
          e.preventDefault();
          try {
            let text = await navigator.clipboard.readText();
            if (this.tab?.socket) {
              const useBracketedPaste =
                this.terminal &&
                this.terminal.modes &&
                this.terminal.modes.bracketedPasteMode;
              if (useBracketedPaste) {
                text = "\x1b[200~" + text + "\x1b[201~";
              }
              if (globalThis.emitPtyInput) {
                globalThis.emitPtyInput(this.tab, text);
              } else {
                this.tab.socket.emit("pty-input", { input: text });
              }
            }
          } catch (err) {
            console.error("Paste failed", err);
          }
          this.menuElement.style.display = "none";
        });

      document.addEventListener("mousedown", (e) => {
        if (
          this.menuElement.style.display === "block" &&
          !e.target.closest("#desktop-context-menu")
        ) {
          this.menuElement.style.display = "none";
        }
      });
    }
  }

  inputNeedsProcess(event, context) {
    if (context.state.isMobile) return false; // Mobile has its own context menu logic currently

    if (event.type === "contextmenu") return true;
    return false;
  }

  processInput(event, context) {
    const e = event.originalEvent;

    // Prevent default right-click menu
    const isTextSelected = globalThis.getSelection().toString().length > 0;
    const isInput =
      e.target.tagName === "INPUT" ||
      e.target.tagName === "TEXTAREA" ||
      e.target.isContentEditable;

    if (isTextSelected || isInput) return false;

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

    if (!allowMenu) {
      e.preventDefault();
      return true;
    }

    if (this.menuElement) {
      e.preventDefault();
      // Show menu at cursor coordinates
      this.menuElement.style.left = `${e.pageX}px`;
      this.menuElement.style.top = `${e.pageY}px`;
      this.menuElement.style.display = "block";
    }

    return true; // Consume event
  }
}
