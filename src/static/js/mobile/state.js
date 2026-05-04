export class MobileModifierState {
  static instance = null;

  constructor() {
    if (MobileModifierState.instance) {
      return MobileModifierState.instance;
    }

    this.ctrlActive = false;
    this.altActive = false;
    this.shiftActive = false;
    this.superActive = false;

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
    this.shiftBtn = replaceBtn("shift-toggle");
    this.superBtn = replaceBtn("super-toggle");

    // Reset visual state on recreation
    if (this.ctrlBtn) this.ctrlBtn.classList.remove("active");
    if (this.altBtn) this.altBtn.classList.remove("active");
    if (this.shiftBtn) this.shiftBtn.classList.remove("active");
    if (this.superBtn) this.superBtn.classList.remove("active");

    this.setupListeners();
    MobileModifierState.instance = this;
  }
  setupListeners() {
    const bindBtn = (btn, toggleFn) => {
      if (!btn) return;
      const handler = (e) => {
        if (e.type === "touchstart" || e.type === "touchend") {
          e.preventDefault();
        }
        if (e.type === "touchstart" || e.type === "mousedown") {
          if (globalThis.triggerHapticFeedback)
            globalThis.triggerHapticFeedback();
          // Focus immediately on touchstart/mousedown to ensure keyboard pops up
          const activeProxy = document.querySelector(".mobile-text-area");
          if (activeProxy) {
            activeProxy.focus();
          }
        }
        if (e.type === "touchend" || e.type === "mousedown") {
          toggleFn();
          // Re-focus on touchend to be absolutely sure
          const activeProxy = document.querySelector(".mobile-text-area");
          if (activeProxy) {
            activeProxy.focus();
          }
        }
      };
      btn.addEventListener("touchstart", handler, { passive: false });
      btn.addEventListener("touchend", handler, { passive: false });
      btn.addEventListener("mousedown", handler);
    };
    bindBtn(this.ctrlBtn, () => this.toggleCtrl());
    bindBtn(this.altBtn, () => this.toggleAlt());
    bindBtn(this.shiftBtn, () => this.toggleShift());
    bindBtn(this.superBtn, () => this.toggleSuper());
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

  toggleShift(force) {
    this.shiftActive = force !== undefined ? force : !this.shiftActive;
    if (this.shiftBtn) {
      if (this.shiftActive) this.shiftBtn.classList.add("active");
      else this.shiftBtn.classList.remove("active");
    }
  }

  toggleSuper(force) {
    this.superActive = force !== undefined ? force : !this.superActive;
    if (this.superBtn) {
      if (this.superActive) this.superBtn.classList.add("active");
      else this.superBtn.classList.remove("active");
    }
  }

  applyModifiers(data) {
    if (!data) return data;
    let input = data;

    if (this.shiftActive && data === "\t") {
      input = "\x1b[Z";
      this.toggleShift(false);
      return input;
    }

    if (this.ctrlActive && data.length === 1) {
      const code = data.codePointAt(0);
      if (code >= 97 && code <= 122) {
        // a-z
        input = String.fromCodePoint(code - 96);
      } else if (code >= 65 && code <= 90) {
        // A-Z
        input = String.fromCodePoint(code - 64);
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

    if (this.superActive && data.length === 1) {
      // Super+key: send as Alt+key if it's a simple character,
      // as Gemini CLI supports Alt+Z for undo.
      input = "\x1b" + input;
      this.toggleSuper(false);
    } else if (this.superActive) {
      this.toggleSuper(false);
    }

    if (this.shiftActive && data.length === 1) {
      const code = data.codePointAt(0);
      if (code >= 97 && code <= 122) {
        input = String.fromCodePoint(code - 32);
      }
      this.toggleShift(false);
    } else if (this.shiftActive) {
      this.toggleShift(false);
    }

    return input;
  }
}
