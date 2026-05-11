import { TerminalModule } from "../pipeline/TerminalModule.js";

export class HotkeyPlugin extends TerminalModule {
  constructor() {
    super("HotkeyPlugin", 85); // Between Copy (90) and Paste (80)
  }

  setup(terminal, tab) {
    this.terminal = terminal;
    this.tab = tab;
  }

  inputNeedsProcess(event, context) {
    if (event.type === "keydown") {
      // Handle Ctrl+Enter or Alt+Enter
      if (
        (event.ctrlKey || event.altKey) &&
        (event.key === "Enter" || event.code === "Enter")
      ) {
        return true;
      }

      // Allow printable characters and backspace to pass through to the textarea overlay
      // so they populate the autocorrect buffer instead of being swallowed by xterm's keydown handler.
      if (
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        event.key &&
        event.key.length === 1
      ) {
        if (context.state.isMobile) return true;
      }
      if (event.key === "Backspace") {
        if (context.state.isMobile) return true;
      }
    }
    return false;
  }

  processInput(event, context) {
    // Handle Ctrl+Enter or Alt+Enter
    if (
      (event.ctrlKey || event.altKey) &&
      (event.key === "Enter" || event.code === "Enter")
    ) {
      if (this.tab.mobileProxy && this.tab.mobileProxy.ui) {
        this.tab.mobileProxy.ui.proxyInput.value += "\x1b\r";
        this.tab.mobileProxy.ui.proxyInput.dispatchEvent(
          new Event("input", { bubbles: true }),
        );
      } else {
        // Fallback for non-mobile if proxy isn't active
        if (this.tab.socket) {
          if (globalThis.emitPtyInput) {
            globalThis.emitPtyInput(this.tab, "\x1b\r");
          } else {
            this.tab.socket.emit("pty-input", { input: "\x1b\r" });
          }
        }
      }
      return true; // Consume event so xterm ignores it
    }

    // For printable characters on mobile, return false so xterm handles it
    // Wait, the original code in attachCustomKeyEventHandler returned `false` for these to tell xterm to ignore them!
    // Returning `true` from this module means the pipeline consumed it, so TerminalPipeline will return `false` to xterm.
    // Let's verify: In attachCustomKeyEventHandler: `if (consumed) { e.preventDefault(); return false; } return true;`
    // Yes! If we want xterm to IGNORE the event (return false to xterm), we must CONSUME it (return true from processInput).
    return true;
  }
}
