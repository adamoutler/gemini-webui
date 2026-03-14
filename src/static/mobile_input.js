class MobileModifierState {
  constructor() {
    this.ctrlActive = false;
    this.altActive = false;
    this.ctrlBtn = document.getElementById("ctrl-toggle");
    this.altBtn = document.getElementById("alt-toggle");
    this.setupListeners();
  }

  setupListeners() {
    const bindBtn = (btn, toggleFn) => {
      if (!btn) return;
      const handler = (e) => {
        if (e.type === "touchstart" || e.type === "touchend")
          e.preventDefault();
        // only toggle on touchstart or mousedown, avoid double toggle
        if (e.type === "touchstart" || e.type === "mousedown") {
          if (window.triggerHapticFeedback) window.triggerHapticFeedback();
          toggleFn();
          const activeProxy = document.querySelector(".mobile-proxy-input");
          if (activeProxy) activeProxy.focus();
        }
      };
      btn.addEventListener("touchstart", handler, { passive: false });
      btn.addEventListener("touchend", handler, { passive: false });
      btn.addEventListener("mousedown", handler);
    };
    bindBtn(this.ctrlBtn, () => this.toggleCtrl());
    bindBtn(this.altBtn, () => this.toggleAlt());
  }

  toggleCtrl(force) {
    this.ctrlActive = force !== undefined ? force : !this.ctrlActive;
    if (this.ctrlBtn) {
      if (this.ctrlActive) this.ctrlBtn.classList.add("active");
      else this.ctrlBtn.classList.remove("active");
    }
  }

  toggleAlt(force) {
    this.altActive = force !== undefined ? force : !this.altActive;
    if (this.altBtn) {
      if (this.altActive) this.altBtn.classList.add("active");
      else this.altBtn.classList.remove("active");
    }
  }

  applyModifiers(data) {
    if (!data) return data;
    let input = data;
    if (this.ctrlActive && data.length === 1) {
      const code = data.charCodeAt(0);
      if (code >= 97 && code <= 122) {
        // a-z
        input = String.fromCharCode(code - 96);
      } else if (code >= 65 && code <= 90) {
        // A-Z
        input = String.fromCharCode(code - 64);
      } else if (code === 32) {
        // Ctrl+Space
        input = "\x00";
      } else if (code === 91) {
        // Ctrl+[
        input = "\x1b";
      } else if (code === 92) {
        // Ctrl+\
        input = "\x1c";
      } else if (code === 93) {
        // Ctrl+]
        input = "\x1d";
      }
      this.toggleCtrl(false);
    } else if (this.ctrlActive) {
      this.toggleCtrl(false);
    }

    if (this.altActive && data.length === 1) {
      input = "\x1b" + input;
      this.toggleAlt(false);
    } else if (this.altActive) {
      this.toggleAlt(false);
    }
    return input;
  }
}

class MobileInputBuffer {
  constructor(emitCallback, isMobile, modifierState) {
    this.emitCallback = emitCallback;
    this.isMobile = isMobile;
    this.modifierState = modifierState;
  }

  handleInput(e, isComposing, value) {
    if (e.inputType === "deleteContentBackward" || e.inputType === "deleteWordBackward") {
      if (!this.isMobile) return undefined;
      // We do not emit backspace here because deleting text within the visible buffer
      // should not delete text already sent to the terminal.
      // Backspacing an empty buffer is handled by handleKeyDown.
      return undefined;
    }

    // If modifiers are active, consume exactly 1 char from data, apply modifiers, emit, clear buffer
    if (
      this.modifierState &&
      (this.modifierState.ctrlActive || this.modifierState.altActive)
    ) {
      const char =
        e.data && e.data.length > 0
          ? e.data[e.data.length - 1]
          : value
            ? value.slice(-1)
            : null;
      if (char) {
        const modified = this.modifierState.applyModifiers(char);
        this.emitCallback(modified);
        // Return the buffer without the consumed character
        return value.slice(0, -1);
      }
    }
    if (isComposing) return undefined;

    const boundaryRegex = /[\s.,?!;-]/;

    if (!this.isMobile && !isComposing) {
      if (e.data && e.data.length === 1) {
        if (boundaryRegex.test(e.data)) {
          return "";
        }
        return undefined;
      }
    }

    if (boundaryRegex.test(value) || (!this.isMobile && value.length > 1)) {
      this.emitCallback(value);
      return "";
    }
    return undefined;
  }

  handleKeyDown(e, value, isComposing) {
    const passthroughKeys = {
      Tab: "\t",
      Escape: "\x1b",
    };

    // If it's an explicit control key, process it even if composing.
    if (passthroughKeys[e.key]) {
      e.preventDefault();
      if (e.key === "Escape") {
        this.emitCallback(passthroughKeys[e.key]);
        return ""; // clear buffer
      } else {
        // Tab completely bypasses buffer, but does not clear it
        this.emitCallback(passthroughKeys[e.key]);
        return undefined; // leave buffer intact
      }
    }

    if (e.altKey || e.ctrlKey || e.metaKey) {
      if (e.key && e.key.length === 1 && !e.metaKey) {
        e.preventDefault();
        let input = e.key;
        if (e.ctrlKey) {
          const code = input.charCodeAt(0);
          if (code >= 97 && code <= 122) input = String.fromCharCode(code - 96);
          else if (code >= 65 && code <= 90)
            input = String.fromCharCode(code - 64);
        }
        if (e.altKey) {
          input = "\x1b" + input;
        }
        this.emitCallback(input);
        return ""; // Ctrl/Alt clear buffer
      }
      if (!this.isMobile) return "";
      return undefined;
    }

    if (isComposing) return undefined;

    if (e.key === "Backspace" || e.keyCode === 8) {
      if (value.length === 0) {
        if (!this.isMobile) return undefined;
        e.preventDefault();
        this.emitCallback("\x7f");
      }
    }
    if (e.key === "Enter") {
      if (!this.isMobile) return undefined;
      e.preventDefault();
      this.emitCallback(value + "\r");
      return "";
    }
    return undefined;
  }
}

class MobileInputUI {
  constructor(tabId, inputHandler, keyDownHandler) {
    let container = document.getElementById("mobile-input-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "mobile-input-container";
      container.className = "mobile-input-container";
      const mobileControls = document.getElementById("mobile-controls");
      if (mobileControls && mobileControls.parentNode) {
        mobileControls.parentNode.insertBefore(container, mobileControls);
      } else {
        document.body.appendChild(container);
      }
    }

    this.proxyInput = document.getElementById("terminal-input-mobile");
    if (!this.proxyInput) {
      this.proxyInput = document.createElement("textarea");
      this.proxyInput.id = "terminal-input-mobile";
      this.proxyInput.className = "mobile-text-area";
      this.proxyInput.placeholder = "Tap to type...";
      
      this.proxyInput.setAttribute("autocomplete", "on");
      this.proxyInput.setAttribute("autocorrect", "on");
      this.proxyInput.setAttribute("spellcheck", "true");
      this.proxyInput.setAttribute("autocapitalize", "sentences");

      container.appendChild(this.proxyInput);
    }

    this.isComposing = false;
    this.proxyInput.addEventListener("compositionstart", () => {
      this.isComposing = true;
      this.proxyInput.classList.add("is-composing");
    });
    this.proxyInput.addEventListener("compositionend", () => {
      this.isComposing = false;
      this.proxyInput.classList.remove("is-composing");
      setTimeout(() => {
        if (this.proxyInput.value.length > 0) this.proxyInput.value = "";
      }, 200);
    });

    this.proxyInput.addEventListener("input", (e) => {
      const newValue = inputHandler(e, this.isComposing, this.proxyInput.value);
      if (newValue !== undefined) this.proxyInput.value = newValue;

      // Auto-commit buffer after pause for dictation
      if (this.dictationTimer) clearTimeout(this.dictationTimer);

      if (this.proxyInput.value.length > 0) {
        const isDictation =
          e.inputType === "insertDictationResult" ||
          (e.data && e.data.length > 5 && e.inputType !== "insertFromPaste");

        this.dictationTimer = setTimeout(
          () => {
            if (this.proxyInput.value.length > 0) {
              // force flush by appending a space
              inputHandler({ data: " " }, false, this.proxyInput.value + " ");
              this.proxyInput.value = "";
            }
          },
          isDictation ? 800 : 2000,
        );
      }
    });
    this.proxyInput.addEventListener("keydown", (e) => {
      const newValue = keyDownHandler(
        e,
        this.proxyInput.value,
        this.isComposing,
      );
      if (newValue !== undefined) this.proxyInput.value = newValue;
    });
  }

  alignWithCursor(term) {
    // We no longer align a floating proxy input with the cursor.
    // The mobile-text-area remains fixed at the bottom.
  }
}

class MobileTerminalController {
  constructor(tab) {
    this.tab = tab;

    this.isMobile =
      window.matchMedia("(max-width: 768px) and (pointer: coarse)").matches ||
      "ontouchstart" in window;

    if (this.isMobile) {
      this.modifierState = new MobileModifierState();
      this.buffer = new MobileInputBuffer(
        this.emitToTerminal.bind(this),
        this.isMobile,
        this.modifierState,
      );
      this.ui = new MobileInputUI(
        this.tab.id,
        this.buffer.handleInput.bind(this.buffer),
        this.buffer.handleKeyDown.bind(this.buffer),
      );

      this.setupFocusManagement();
    }
  }

  setupFocusManagement() {
    if (!this.tab.term) return;

    // Intercept touch events on terminal to focus our proxy instead
    this.tab.term.element.addEventListener("touchstart", (e) => {
      if (!e.target.closest(".xterm-viewport")) {
        e.preventDefault(); // disable xterm's native textarea behavior
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
    if (!this.tab || !this.tab.socket || data == null) return;
    if (window.emitPtyInput) {
      window.emitPtyInput(this.tab, data);
    } else {
      const chunkSize = 1024;
      const strData = String(data).replace(/\n/g, "\r");
      for (let i = 0; i < strData.length; i += chunkSize) {
        const chunk = strData.slice(i, i + chunkSize);
        this.tab.socket.emit("pty-input", { input: chunk });
      }
    }
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    MobileInputBuffer,
    MobileInputUI,
    MobileTerminalController,
    MobileModifierState,
  };
}
