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
};

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
      const items = (e.clipboardData || window.clipboardData)?.items;
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

      let pasteText = (e.clipboardData || window.clipboardData).getData("text");
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
        "button, a, input, select, .control-btn, .header-icon",
      );
      if (!isInteractive && window.activeTabId === this.tab.id) {
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
    window.addEventListener("resize", () =>
      this.ui.alignWithCursor(this.tab.term),
    );
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", () =>
        this.ui.alignWithCursor(this.tab.term),
      );
      window.visualViewport.addEventListener("scroll", () =>
        this.ui.alignWithCursor(this.tab.term),
      );
    }
  }

  emitToTerminal(data) {
    const activeTab = window.tabs
      ? window.tabs.find((t) => t.id === window.activeTabId)
      : this.tab;
    const targetTab = activeTab || this.tab;

    if (!targetTab || !targetTab.socket || data == null) return;
    if (window.emitPtyInput) {
      window.emitPtyInput(targetTab, data);
    } else {
      const strData = String(data).replace(/\n/g, "\r");
      targetTab.socket.emit("pty-input", { input: strData });
    }
  }
}

// Global exposure to support traditional browser logic (like app.js) before a full ESM refactor:
if (typeof window !== "undefined") {
  window.MobileTerminalController = MobileTerminalController;
  window.MobileModifierState = MobileModifierState;
  window.MobileInputBuffer = MobileInputBuffer;
  window.MobileInputUI = MobileInputUI;
  window.InputRule = InputRule;
  window.ExtensionRuleParser = ExtensionRuleParser;
  window.BackspaceRule = BackspaceRule;
  window.ModifierRule = ModifierRule;
  window.WordBoundaryRule = WordBoundaryRule;
}

// Manual pull-to-refresh on toolbar
if (
  typeof document !== "undefined" &&
  typeof document.addEventListener === "function"
) {
  document.addEventListener("DOMContentLoaded", () => {
    const toolbar = document.getElementById("toolbar");
    if (!toolbar) return;

    let startY = 0;
    let isPulling = false;

    toolbar.addEventListener(
      "touchstart",
      (e) => {
        if (
          e.touches.length === 1 &&
          document.documentElement.scrollTop === 0
        ) {
          startY = e.touches[0].clientY;
          isPulling = true;
        }
      },
      { passive: true },
    );

    toolbar.addEventListener(
      "touchmove",
      (e) => {
        if (!isPulling) return;
        const y = e.touches[0].clientY;
        if (y - startY > 150) {
          window.location.reload();
          isPulling = false;
        }
      },
      { passive: true },
    );

    toolbar.addEventListener("touchend", () => {
      isPulling = false;
    });
  });
}
