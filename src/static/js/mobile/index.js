import { MobileModifierState } from "./state.js";
import {
  InputRule,
  ExtensionRuleParser,
  CursorPlacementRule,
  BackspaceRule,
  ModifierRule,
  WordBoundaryRule,
} from "./rules.js";
import { MobileInputBuffer, MobileInputUI } from "./ui.js";
import { PullToRefresh } from "./pull-to-refresh.js";

export {
  MobileModifierState,
  InputRule,
  ExtensionRuleParser,
  CursorPlacementRule,
  BackspaceRule,
  ModifierRule,
  WordBoundaryRule,
  MobileInputBuffer,
  MobileInputUI,
  PullToRefresh,
};

// Initialize the pull-to-refresh module
new PullToRefresh(["toolbar", "tab-bar"], "ptr-indicator");

export class MobileTerminalController {
  constructor(tab) {
    this.tab = tab;

    this.isMobile = document.documentElement.classList.contains("is-mobile");

    if (this.isMobile) {
      this.modifierState = new MobileModifierState();

      this.ruleParser = new ExtensionRuleParser({
        emitToTerminal: this.emitToTerminal.bind(this),
        getProxyInput: () => (this.ui ? this.ui.proxyInput : null),
        modifierState: this.modifierState,
        term: tab.term,
      });
      this.ruleParser.registerRule(new CursorPlacementRule());
      this.ruleParser.registerRule(new BackspaceRule());
      this.ruleParser.registerRule(new ModifierRule());
      this.ruleParser.registerRule(new WordBoundaryRule());

      this.buffer = new MobileInputBuffer(
        this.emitToTerminal.bind(this),
        this.isMobile,
        this.modifierState,
      );
      this.ui = new MobileInputUI(
        this.tab.id,
        this.buffer.handleInput.bind(this.buffer),
        this.buffer.handleKeyDown.bind(this.buffer),
        this.ruleParser,
      );
      this.ruleParser.context.ui = this.ui;

      this.setupFocusManagement();
    }
  }

  setupFocusManagement() {
    if (!this.tab.term) return;

    // Disable xterm's native textarea on mobile so it cannot steal focus
    // and cause the mobile keyboard to flash on re-taps.
    const nativeTextarea = this.tab.term.textarea;
    if (nativeTextarea && this.isMobile) {
      nativeTextarea.disabled = true;
      nativeTextarea.style.display = "none";
    }
    // Handle paste directly on our proxy input since we disabled xterm's textarea
    this.ui.proxyInput.addEventListener("paste", async (e) => {
      const items = (e.clipboardData || globalThis.clipboardData)?.items;
      let hasImage = false;
      if (items) {
        for (let i = 0; i < items.length; i++) {
          const item = items[i];
          if (item.type.startsWith("image/")) {
            hasImage = true;
            e.preventDefault();
            const file = item.getAsFile();
            if (!file) continue;

            if (typeof uploadPastedImage === "function") {
              await uploadPastedImage(
                file,
                this.tab,
                this.emitToTerminal.bind(this),
              );
            } else {
              this.emitToTerminal(
                `\r\n\x1b[31m[Error] uploadPastedImage function not available.\x1b[0m\r\n`,
              );
            }
          }
        }
      }

      if (hasImage) return;

      let pasteText = (e.clipboardData || globalThis.clipboardData).getData(
        "text",
      );
      if (pasteText) {
        e.preventDefault();

        // Use bracketed paste if enabled by terminal
        const useBracketedPaste =
          this.tab.term &&
          this.tab.term.modes &&
          this.tab.term.modes.bracketedPasteMode;
        if (useBracketedPaste) {
          pasteText = "\x1b[200~" + pasteText + "\x1b[201~";
        }

        // WARNING: Large pastes on mobile must be chunked (like xterm.js natively does)
        // to prevent overwhelming the Python PTY backend's O_NONBLOCK os.write buffer,
        // which truncates large payloads. We chunk at 1024 chars every 10ms.
        this.ui.proxyInput.value = ""; // Clear proxy buffer to avoid duplicates

        const chunkSize = 1024;
        let offset = 0;
        const sendChunk = () => {
          if (offset >= pasteText.length) return;
          const chunk = pasteText.slice(offset, offset + chunkSize);
          this.emitToTerminal(chunk);
          offset += chunkSize;
          setTimeout(sendChunk, 10);
        };
        sendChunk();
      }
    });
    // Use a click listener on the document to focus our proxy input if they tap anywhere.
    // A standard click event reliably detects a tap (vs a long-press/scroll).
    document.addEventListener("click", (e) => {
      if (!this.isMobile) return;
      // Do not steal focus if they clicked a button, link, or another input
      const target = e.target;
      const isInteractive = target.closest(
        "button, a, input, select, textarea, .control-btn, .header-icon, .modal, .swal2-container",
      );
      if (!isInteractive && globalThis.activeTabId === this.tab.id) {
        this.ui.proxyInput.focus();
        this.ui.alignWithCursor(this.tab.term);
      }
    });

    // Update alignment when cursor moves
    this.tab.term.onCursorMove(() => {
      this.ui.alignWithCursor(this.tab.term);
    });

    // Update alignment when proxy input changes (in case width/opacity needs changing)
    this.ui.proxyInput.addEventListener("input", () => {
      this.ui.alignWithCursor(this.tab.term);
    });

    // Re-align on terminal scroll
    const viewport = this.tab.term.element.querySelector(".xterm-viewport");
    if (viewport) {
      viewport.addEventListener("scroll", () => {
        this.ui.alignWithCursor(this.tab.term);
      });
    }

    // Re-align on resize or scroll
    globalThis.addEventListener("resize", () =>
      this.ui.alignWithCursor(this.tab.term),
    );
    if (globalThis.visualViewport) {
      globalThis.visualViewport.addEventListener("resize", () =>
        this.ui.alignWithCursor(this.tab.term),
      );
      globalThis.visualViewport.addEventListener("scroll", () =>
        this.ui.alignWithCursor(this.tab.term),
      );
    }
  }

  emitToTerminal(data) {
    const activeTab = globalThis.tabs
      ? globalThis.tabs.find((t) => t.id === globalThis.activeTabId)
      : this.tab;
    const targetTab = activeTab || this.tab;

    if (!targetTab || !targetTab.socket || data == null) return;
    if (globalThis.emitPtyInput) {
      globalThis.emitPtyInput(targetTab, data);
    } else {
      const strData = String(data).replaceAll("\n", "\r");
      targetTab.socket.emit("pty-input", { input: strData });
    }
  }
}

// Global exposure to support traditional browser logic (like app.js) before a full ESM refactor:
if (typeof globalThis.window !== "undefined") {
  globalThis.MobileTerminalController = MobileTerminalController;
  globalThis.MobileModifierState = MobileModifierState;
  globalThis.MobileInputBuffer = MobileInputBuffer;
  globalThis.MobileInputUI = MobileInputUI;
  globalThis.InputRule = InputRule;
  globalThis.ExtensionRuleParser = ExtensionRuleParser;
  globalThis.BackspaceRule = BackspaceRule;
  globalThis.ModifierRule = ModifierRule;
  globalThis.WordBoundaryRule = WordBoundaryRule;
}
