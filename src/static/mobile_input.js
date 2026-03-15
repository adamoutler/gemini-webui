class MobileModifierState {
  static instance = null;

  constructor() {
    if (MobileModifierState.instance) {
      return MobileModifierState.instance;
    }

    this.ctrlActive = false;
    this.altActive = false;

    // Clone and replace buttons to strip old event listeners from previous connections
    const replaceBtn = (id) => {
      const btn = document.getElementById(id);
      if (!btn) return null;
      const newBtn = btn.cloneNode(true);
      btn.parentNode.replaceChild(newBtn, btn);
      return newBtn;
    };

    this.ctrlBtn = replaceBtn("ctrl-toggle");
    this.altBtn = replaceBtn("alt-toggle");

    // Reset visual state on recreation
    if (this.ctrlBtn) this.ctrlBtn.classList.remove("active");
    if (this.altBtn) this.altBtn.classList.remove("active");

    this.setupListeners();
    MobileModifierState.instance = this;
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
          const activeProxy = document.querySelector(".mobile-text-area");
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
    this.lastEmittedText = "";
  }

  handleInput(
    e,
    isComposing,
    value,
    forceEmit = false,
    lastValue = "",
    isDictation = false,
  ) {
    if (
      e.inputType === "deleteContentBackward" ||
      e.inputType === "deleteWordBackward"
    ) {
      if (!this.isMobile) return undefined;
      // If the buffer was ALREADY empty before this delete event,
      // it means the user pressed backspace on an empty buffer.
      if (lastValue.length === 0) {
        this.emitCallback("\x7f");
        // We also need to shrink lastEmittedText so commonPrefix logic doesn't break
        if (this.lastEmittedText && this.lastEmittedText.length > 0) {
          this.lastEmittedText = this.lastEmittedText.substring(
            0,
            this.lastEmittedText.length - 1,
          );
        }
        return ""; // Force clear so Gboard's resurrected text is deleted
      }
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
        this.lastEmittedText = ""; // reset on modifier
        // Return the buffer without the consumed character
        return value.slice(0, -1);
      }
    }

    // Gboard remembers the entire line of text and re-inserts it.
    // Find the common prefix between what we previously emitted and what Gboard thinks is there.
    let i = 0;
    const prevEmit = this.lastEmittedText || "";
    while (
      i < prevEmit.length &&
      i < value.length &&
      prevEmit[i] === value[i]
    ) {
      i++;
    }

    // The actual text Gboard thinks is in the buffer up to the point it diverges
    this.lastEmittedText = prevEmit.substring(0, i);

    // The "new" text that hasn't been emitted yet
    let workingValue = value.substring(i);

    const boundaryRegex = /[\s.,?!;—，。？！；]$/; // Match boundary at the END

    // If it's a dictation (voice typing), we don't clear on every space.
    // We let the dictationTimer or forceEmit handle the final flush.
    if (isDictation && !forceEmit) {
      return workingValue !== value ? workingValue : undefined;
    }

    // For normal typing, we check if the value ends with a boundary.
    // We flush on boundary to enforce a single-word buffer.
    if (
      forceEmit ||
      boundaryRegex.test(workingValue) ||
      (!this.isMobile && workingValue.length > 1)
    ) {
      this.emitCallback(workingValue);
      this.lastEmittedText += workingValue;
      return "";
    }

    // If we stripped text, we must return the stripped version so the textarea updates
    return workingValue !== value ? workingValue : undefined;
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

    let oldProxy = document.getElementById("terminal-input-mobile");
    if (oldProxy) oldProxy.remove();

    this.proxyInput = document.createElement("textarea");
    this.proxyInput.id = "terminal-input-mobile";
    this.proxyInput.className = "mobile-text-area";
    this.proxyInput.placeholder = "";

    // Make it visible, transparent background, positioned at cursor
    this.proxyInput.style.position = "absolute";
    this.proxyInput.style.opacity = "1";
    this.proxyInput.style.zIndex = "100";
    this.proxyInput.style.height = "2em"; // Enough for one line
    this.proxyInput.style.whiteSpace = "pre-wrap";
    this.proxyInput.style.wordBreak = "break-word";
    this.proxyInput.style.background = "transparent";
    this.proxyInput.style.color = "inherit";

    this.proxyInput.setAttribute("autocomplete", "on");
    this.proxyInput.setAttribute("autocorrect", "on");
    this.proxyInput.setAttribute("spellcheck", "true");
    this.proxyInput.setAttribute("autocapitalize", "sentences");

    container.appendChild(this.proxyInput);
    this.isComposing = false;
    this.proxyInput.addEventListener("compositionstart", () => {
      this.isComposing = true;
      this.proxyInput.classList.add("is-composing");
    });
    let lastValue = this.proxyInput.value;

    this.proxyInput.addEventListener("compositionend", () => {
      this.isComposing = false;
      this.proxyInput.classList.remove("is-composing");
      // Give the native input event a moment to fire and settle,
      // then flush the buffer to terminal if it's not empty.
      setTimeout(() => {
        if (this.proxyInput.value.length > 0) {
          // Send whatever was composed and clear the proxy
          inputHandler(
            { data: "" },
            false,
            this.proxyInput.value,
            true,
            lastValue,
          );
          this.proxyInput.value = "";
          lastValue = "";
        }
      }, 50);
    });

    this.proxyInput.addEventListener("input", (e) => {
      const currentValue = this.proxyInput.value;
      const newValue = inputHandler(
        e,
        this.isComposing,
        currentValue,
        false,
        lastValue,
      );
      if (newValue !== undefined) {
        this.proxyInput.value = newValue;
      }
      lastValue = this.proxyInput.value;

      // Auto-commit buffer after pause for dictation
      if (this.dictationTimer) {
        clearTimeout(this.dictationTimer);
        this.dictationTimer = null;
      }

      if (this.proxyInput.value.length > 0) {
        const isDictation =
          e.inputType === "insertDictationResult" ||
          (e.data && e.data.length > 5 && e.inputType !== "insertFromPaste");

        if (isDictation) {
          this.dictationTimer = setTimeout(() => {
            if (this.proxyInput.value.length > 0) {
              // force flush
              inputHandler(
                { data: "" },
                false,
                this.proxyInput.value,
                true,
                this.proxyInput.value,
                true,
              );
              this.proxyInput.value = "";
              lastValue = "";
            }
          }, 800);
        }
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
    if (!term || !this.proxyInput) return;
    const cursor = term.element.querySelector(".xterm-cursor");
    if (cursor) {
      const rect = cursor.getBoundingClientRect();
      this.proxyInput.style.left = `${rect.left}px`;
      this.proxyInput.style.top = `${rect.top}px`;
      const remainingWidth = window.innerWidth - rect.left;
      this.proxyInput.style.width = `${Math.max(remainingWidth, 50)}px`;

      // Match terminal font metrics if possible
      const termEl = term.element.querySelector(".xterm-rows");
      if (termEl) {
        const style = window.getComputedStyle(termEl);
        this.proxyInput.style.fontFamily = style.fontFamily;
        this.proxyInput.style.fontSize = style.fontSize;
        this.proxyInput.style.lineHeight = style.lineHeight;
        this.proxyInput.style.letterSpacing = style.letterSpacing;
      }
    }
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

    // Disable xterm's native textarea on mobile so it cannot steal focus
    // and cause the mobile keyboard to flash on re-taps.
    const nativeTextarea = this.tab.term.textarea;
    if (nativeTextarea && this.isMobile) {
      nativeTextarea.disabled = true;
      nativeTextarea.style.display = "none";
    }

    // Prevent default on touchstart/mousedown so tapping the terminal doesn't blur the input
    const preventBlur = (e) => {
      if (this.isMobile && e.target.closest(".xterm-viewport")) {
        // Only prevent default if we're not tapping on something that naturally needs focus
        e.preventDefault();
        this.ui.proxyInput.focus();
        this.ui.alignWithCursor(this.tab.term);
      }
    };

    this.tab.term.element.addEventListener("touchstart", preventBlur, {
      passive: false,
    });
    this.tab.term.element.addEventListener("mousedown", preventBlur);

    // Use a click listener on the terminal to focus our proxy input
    this.tab.term.element.addEventListener("click", () => {
      if (this.isMobile) {
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
    const activeTab = window.tabs
      ? window.tabs.find((t) => t.id === window.activeTabId)
      : this.tab;
    const targetTab = activeTab || this.tab;

    if (!targetTab || !targetTab.socket || data == null) return;
    if (window.emitPtyInput) {
      window.emitPtyInput(targetTab, data);
    } else {
      const chunkSize = 1024;
      const strData = String(data).replace(/\n/g, "\r");
      for (let i = 0; i < strData.length; i += chunkSize) {
        const chunk = strData.slice(i, i + chunkSize);
        targetTab.socket.emit("pty-input", { input: chunk });
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
