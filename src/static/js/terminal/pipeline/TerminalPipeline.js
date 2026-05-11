export class TerminalPipeline {
  constructor(terminal, tab) {
    this.modules = [];
    this.terminal = terminal;
    this.tab = tab;
    this.disposables = [];

    // Terminal Context exposed to modules
    this.context = {
      state: {
        get hasSelection() {
          return terminal.hasSelection();
        },
        get isMobile() {
          return document.documentElement.classList.contains("is-mobile");
        },
        isReadOnly: false,
        isComposing: false,
      },
      api: {
        getSelection: () => terminal.getSelection(),
        clearSelection: () => terminal.clearSelection(),
        writeToTerminal: (data) => terminal.write(data),
        sendDataToServer: (data) => {
          if (tab.mobileProxy && tab.mobileProxy.ui) {
            tab.mobileProxy.ui.proxyInput.value += data;
            tab.mobileProxy.ui.proxyInput.dispatchEvent(
              new Event("input", { bubbles: true }),
            );
          } else if (globalThis.emitPtyInput) {
            globalThis.emitPtyInput(tab, data);
          } else if (tab.socket) {
            tab.socket.emit("pty-input", { input: data });
          }
        },
        getTab: () => tab,
      },
    };

    this._bindEvents();
  }

  _bindEvents() {
    // 1. Composition state tracking for IME
    const handleCompositionStart = () => {
      this.context.state.isComposing = true;
    };
    const handleCompositionEnd = () => {
      this.context.state.isComposing = false;
    };

    // 2. Keyboard and Mouse interception via xterm.js custom event handler
    // We attach this directly so we can catch keys before xterm handles them natively.
    this.terminal.attachCustomKeyEventHandler((e) => {
      // Create a normalized event wrapper
      const normalized = {
        type: e.type,
        originalEvent: e,
        key: e.key,
        code: e.code,
        ctrlKey: e.ctrlKey,
        shiftKey: e.shiftKey,
        altKey: e.altKey,
        metaKey: e.metaKey,
      };

      const consumed = this._runInputPipeline(normalized);
      // If a module consumed the keydown, return false to tell xterm to ignore it.
      if (consumed) {
        e.preventDefault();
        return false;
      }
      return true; // Let xterm handle it normally
    });

    // We also need to intercept DOM events that aren't keys (like paste, contextmenu)
    const domHandler = (e) => {
      const normalized = {
        type: e.type,
        originalEvent: e,
      };
      const consumed = this._runInputPipeline(normalized);
      if (consumed) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    // Attach to the terminal's DOM element for mouse/paste events
    if (this.terminal.element) {
      this.terminal.element.addEventListener("paste", domHandler, true);
      this.terminal.element.addEventListener("copy", domHandler, true);
      this.terminal.element.addEventListener("contextmenu", domHandler, true);
      this.terminal.element.addEventListener("mousedown", domHandler, true);

      this.disposables.push(() => {
        this.terminal.element.removeEventListener("paste", domHandler, true);
        this.terminal.element.removeEventListener("copy", domHandler, true);
        this.terminal.element.removeEventListener(
          "contextmenu",
          domHandler,
          true,
        );
        this.terminal.element.removeEventListener(
          "mousedown",
          domHandler,
          true,
        );
      });
    }

    // Bind composition handlers to window to catch IME anywhere
    window.addEventListener("compositionstart", handleCompositionStart);
    window.addEventListener("compositionend", handleCompositionEnd);

    this.disposables.push(() => {
      window.removeEventListener("compositionstart", handleCompositionStart);
      window.removeEventListener("compositionend", handleCompositionEnd);
    });
  }

  registerModule(module) {
    module.setup(this.terminal, this.tab);
    this.modules.push(module);
    // Sort modules by descending priority
    this.modules.sort((a, b) => b.priority - a.priority);
  }

  _runInputPipeline(event) {
    // If the system is actively composing an IME input, don't intercept typing events
    if (
      this.context.state.isComposing &&
      (event.type === "keydown" || event.type === "keyup")
    ) {
      return false;
    }

    for (const module of this.modules) {
      if (module.inputNeedsProcess(event, this.context)) {
        if (module.processInput(event, this.context)) {
          return true; // Event was consumed by this module
        }
      }
    }
    return false; // Event passed through all modules
  }

  dispose() {
    for (const module of this.modules) {
      module.dispose();
    }
    this.disposables.forEach((d) => d());
    this.modules = [];
  }
}
