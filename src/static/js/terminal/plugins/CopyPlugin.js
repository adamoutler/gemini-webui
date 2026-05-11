export class CopyPlugin {
  activate(terminal) {
    this.terminal = terminal;
    this._disposables = [];

    const handler = (e) => {
      if (
        e.type === "keydown" &&
        e.ctrlKey &&
        e.shiftKey &&
        (e.key === "c" || e.key === "C" || e.code === "KeyC")
      ) {
        const selection = this.terminal.getSelection();
        if (selection) {
          navigator.clipboard.writeText(
            globalThis.filterTerminalFluff
              ? globalThis.filterTerminalFluff(selection)
              : selection,
          );
        } else {
          document.execCommand("copy");
        }
        e.preventDefault();
        e.stopPropagation();
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
