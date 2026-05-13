# src/static/js/mobile Module

## Purpose

The `src/static/js/mobile` directory implements a highly specialized input layer designed to solve the notorious difficulties of using standard terminal emulators (like xterm.js) on mobile devices, particularly Android. It bridges the gap between touch-based software keyboards (which rely heavily on IME composition, autocorrect, and predictive text) and the character-by-character input expected by PTYs.

## General Themes

- **Proxy Input Strategy**: The core mechanism is bypassing xterm.js's native hidden textarea. Instead, a custom `textarea` (the "proxy input") is created, dynamically positioned precisely over the terminal cursor, and made transparent. This allows the native mobile keyboard to capture text, apply autocorrect, and handle dictation normally.
- **Rule-Based Parsing**: Keystrokes and text inputs are not sent blindly to the server. They are passed through an `ExtensionRuleParser` which buffers text until word boundaries (spaces, punctuation) are reached, ensuring predictive text has time to resolve before committing bytes to the PTY.
- **Virtual Modifiers**: Manages the state of on-screen modifier keys (Ctrl, Alt) via `MobileModifierState`, translating taps into the correct escape sequences when combined with standard input.
- **Viewport Stabilization**: Addresses the jarring visual shifts caused by the software keyboard appearing/disappearing by intercepting `visualViewport` resize events and programmatically adjusting the terminal's height and scroll position.

## Module Contracts & APIs

### `index.js` (Orchestrator)

- **Contract**: The entry point that binds the mobile UI, rules, and state to a specific `Terminal` instance.
- **`MobileTerminalController`**: Orchestrates the proxy input, attaches event listeners, and manages the lifecycle of the mobile adaptations.

### `ui.js` (Presentation & Capture)

- **Contract**: Manages the DOM elements required for the proxy input and custom overlays.
- **`MobileInputUI`**: Creates the proxy textarea and the custom touch overlay.
- **`alignWithCursor(term)`**: A critical method that calculates the exact pixel coordinates of the xterm.js cursor and moves the proxy textarea to overlap it perfectly.

### `rules.js` (Input Logic)

- **Contract**: Defines how raw DOM input events are translated into terminal commands.
- **`ExtensionRuleParser`**: Evaluates incoming text against a series of rules.
- **`WordBoundaryRule`**: Flushes the buffered text to the server only when a space or punctuation mark is typed, allowing for natural autocorrect behavior on the preceding word.
- **`CursorPlacementRule`**: Attempts to handle tap-to-reposition logic (though this is notoriously difficult in a terminal environment).

### `state.js` (Modifier Management)

- **Contract**: Tracks the active state of virtual modifier keys.
- **`MobileModifierState`**: A singleton that records whether Ctrl or Alt are "sticky" (active for the next keypress) and provides helper methods to generate the resulting ANSI escape sequences.

### `mobile-input-extra.js` (Environment & Stabilization)

- **Contract**: Provides environment detection and handles OS-level quirks.
- **`isMobile()`**: Robust detection logic for mobile user agents.
- **`updateViewport()`**: Interacts with the `window.visualViewport` API to calculate the true visible area when the software keyboard is active, resizing the terminal container to prevent overlapping or hidden text.

## Internal Dependencies

- **`src/static/js/terminal/pty.js`**: Relies on `emitPtyInput` to send the parsed and buffered text to the server.
- **`src/static/js/core/api.js`**: Utilizes API helpers for logging and configuration.

## External Dependencies

- **`src/static/js/terminal/ui.js`**: The `startSession` function initializes the `MobileTerminalController` if it detects a mobile environment.
- **`src/templates/partials/mobile_controls.html`**: The UI components defined here interact heavily with `state.js` to trigger modifier states.
