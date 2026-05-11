export class PastePlugin {
  constructor(tab) {
    this.tab = tab;
  }

  activate(terminal) {
    this.terminal = terminal;
    this._disposables = [];

    const handler = (e) => {
      if (
        e.type === "keydown" &&
        e.ctrlKey &&
        e.shiftKey &&
        (e.key === "v" || e.key === "V" || e.code === "KeyV")
      ) {
        e.preventDefault();
        e.stopPropagation();

        navigator.clipboard
          .readText()
          .then((text) => {
            if (text) {
              const useBracketedPaste =
                this.terminal &&
                this.terminal.modes &&
                this.terminal.modes.bracketedPasteMode;
              if (useBracketedPaste) {
                text = "\x1b[200~" + text + "\x1b[201~";
              }
              if (this.tab.mobileProxy && this.tab.mobileProxy.ui) {
                this.tab.mobileProxy.ui.proxyInput.value += text;
                this.tab.mobileProxy.ui.proxyInput.dispatchEvent(
                  new Event("input", { bubbles: true }),
                );
              } else if (globalThis.emitPtyInput) {
                globalThis.emitPtyInput(this.tab, text);
              } else if (this.tab.socket) {
                this.tab.socket.emit("pty-input", { input: text });
              }
            }
          })
          .catch((err) => console.error("Paste error", err));
      }
    };

    this.terminal.element.addEventListener("keydown", handler, true);
    this._disposables.push({
      dispose: () =>
        this.terminal.element.removeEventListener("keydown", handler, true),
    });
  }

  dispose() {
    this._disposables.forEach((d) => d.dispose());
  }
}
