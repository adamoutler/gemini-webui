# 🏛️ Terminal Architecture Mandate

## 🚨 CRITICAL ARCHITECTURAL INVARIANT: THE PIPELINE MANDATE 🚨

This directory utilizes a strict **Middleware Pipeline Architecture** (`TerminalPipeline`) for all terminal interactions.

**ABSOLUTE RULE: You are FORBIDDEN from attaching raw event listeners (e.g., `term.onKey`, `term.onData`, `term.attachCustomKeyEventHandler`) directly to the xterm.js instance.**

### The Standard

Every new feature, behavior modification, or interaction intercept MUST be written as an isolated `TerminalModule` and registered in `src/static/js/terminal/plugins/index.js` or directly via `TerminalPipeline`.

### Module Contract

1. Extend `TerminalModule`.
2. Implement `setup()`, `dispose()`, `inputNeedsProcess()`, and `processInput()`.
3. **Consume Responsibly**: If your module successfully handles an input (e.g., intercepting `Ctrl+C`), `processInput()` MUST return `true` to halt the pipeline and prevent the PTY from receiving the character. Return `false` to let it pass through.

_If it touches terminal input/output, it goes in a Plugin. No exceptions._
