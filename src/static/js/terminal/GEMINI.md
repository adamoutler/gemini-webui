# src/static/js/terminal Module

## 🚨 CRITICAL ARCHITECTURAL INVARIANT: THE PIPELINE MANDATE 🚨

This directory strictly enforces a **Middleware Pipeline Architecture** (`TerminalPipeline`) for all terminal interactions.
**ABSOLUTE RULE: You are FORBIDDEN from attaching raw event listeners (e.g., `term.onKey`, `term.onData`, `term.attachCustomKeyEventHandler`) directly to the xterm.js instance.**

## Purpose

This directory houses the core frontend terminal emulation logic, wrapping the `xterm.js` library. It manages the lifecycle of terminal sessions, handles high-throughput Socket.IO communication, and implements an extensible plugin system to intercept and augment terminal behavior (like copy/paste, context menus, and hotkeys) safely.

## General Themes

- **Event Interception via Pipeline**: All keyboard, mouse, and input events bound for the terminal must pass through the `TerminalPipeline`. Modules can inspect, modify, or consume these events before they reach `xterm.js` or the server.
- **High-Performance Rendering**: Implements "burst mode" handling (`_bursting` flags, DOM requestAnimationFrame syncing) to process massive influxes of data (e.g., `cat /dev/urandom`) without locking the browser's main thread. Includes a telemetry loop to warn about frame drops.
- **Cross-Platform Adaptation**: Acts as the boundary where desktop interactions (native copy/paste) and mobile interactions (proxy textarea, virtual modifiers) are reconciled and standardized before hitting the backend PTY.
- **Session Lifecycle Management**: Tightly integrated with Socket.IO to handle reconnects, session reclamation, and graceful degradation during network instability.

## Module Contracts & APIs

### `pipeline/TerminalPipeline.js` (The Engine)

- **Contract**: The central nervous system of the terminal. It intercepts all relevant DOM events (keydown, paste, contextmenu) attached to the xterm wrapper and routes them through registered `TerminalModule` instances based on priority.
- **Behavior**: Creates a `TerminalContext` object for each event. If a module's `processInput()` returns `true`, the pipeline halts, and the event is consumed (preventing default xterm.js behavior).

### `pipeline/TerminalModule.js` (The Interface)

- **Contract**: The abstract base class for all terminal plugins.
- **Methods to Implement**:
  - `setup(terminal, tab)`: Called during initialization.
  - `inputNeedsProcess(event, context)`: Returns boolean indicating if the module cares about the event.
  - `processInput(event, context)`: Handles the event. Must return `true` to consume the event, or `false` to let it pass to the next module.

### `plugins/` (Feature Implementations)

- **`CopyPlugin.js`**: Intercepts `Ctrl+C` (or `Cmd+C`). If text is selected in the terminal, it copies it to the clipboard (and consumes the event). Otherwise, it passes the interrupt signal to the PTY.
- **`PastePlugin.js`**: Intercepts `Ctrl+V` (or `Cmd+V`) and native paste events, routing clipboard text securely to the PTY.
- **`ContextMenuPlugin.js`**: Intercepts right-clicks to present custom contextual options.
- **`HotkeyPlugin.js`**: Catches specific browser-level hotkeys (like zooming or finding) to prevent them from interfering with terminal applications like `vim` or `nano`.

### `ui.js` (Lifecycle & Orchestration)

- **Contract**: Manages the creation, destruction, and resizing of the `xterm.js` instances.
- **`startSession(...)`**: The massive factory function that instantiates `Terminal`, configures addons (FitAddon, WebglAddon), establishes the Socket.IO connection, and wires up the `TerminalPipeline`.
- **`fitTerminal()`**: Calculates the available DOM space and synchronizes the columns/rows with the backend PTY.

### `pty.js` (Communication)

- **Contract**: Handles the outbound transmission of data from the frontend to the backend.
- **`emitPtyInput(tab, input)`**: The standard method for sending strings/bytes to the PTY. It incorporates logic for terminal locking (preventing input during automated tasks) and integrating `MobileModifierState`.

## Internal Dependencies

- **`xterm.js`**: The underlying terminal emulator library.
- **`src/static/js/mobile/index.js`**: `ui.js` initializes `MobileTerminalController` if it detects a mobile viewport.
- **`src/static/js/core/state.js`**: Reads global application state to configure terminal themes and fonts.

## External Dependencies

- **`src/gateways/terminal_socket.py`**: The backend counterpart that receives `pty-input` and emits `pty-output`.
