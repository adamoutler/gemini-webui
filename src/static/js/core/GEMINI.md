# src/static/js/core Module

## Purpose

The `src/static/js/core` directory is the architectural heart of the Gemini WebUI frontend. It provides the foundational infrastructure that supports all other client-side modules. It handles critical low-level concerns such as networking, state management, real-time communication, and browser integration (PWA), ensuring a consistent and secure environment for the UI and Terminal layers.

## General Themes

- **Centralized Application State**: Moves away from scattered, DOM-based state into a unified `globalState` object, making data flow predictable and debuggable.
- **Secure Networking by Default**: Implements strict CSRF protection by globally intercepting and wrapping standard `fetch` calls. The UI layer never has to worry about token management.
- **Decoupling via EventBus**: Uses a Publish/Subscribe pattern to allow disparate parts of the application to interact without direct imports or circular dependencies.
- **Robust Real-Time Communication**: Encapsulates Socket.IO connection logic, including sophisticated reconnect handling and automated CSRF token refreshment during network flaps.

## Module Contracts & APIs

### `api.js` (Networking Layer)

- **Contract**: The sole gateway for HTTP communication.
- **Behavior**:
  - Overwrites `window.fetch` with `customFetch`, ensuring every request includes the anti-CSRF token.
  - Implements `refreshCsrfToken` to gracefully recover from expired sessions by requesting a new token and retrying failed requests.
  - Provides utility functions like `filterTerminalFluff` and `escapeHtml`.

### `state.js` (Data Store)

- **Contract**: Holds the definitive state of the application.
- **Behavior**: Exports `globalState` containing active tabs, themes, fonts, and cached prompts. It also acts as a compatibility bridge, selectively exposing state to the legacy `window` object for older scripts.

### `event-bus.js` (Communication Backbone)

- **Contract**: A simple, synchronous Pub/Sub implementation.
- **Behavior**: Modules use `EventBus.on()` to register listeners and `EventBus.emit()` to broadcast actions. This is heavily utilized by `main.js` to route HTML `data-onclick` events to the correct module.

### `socket.js` (WebSocket Manager)

- **Contract**: Manages the singleton Socket.IO connection for the global launcher/management channel.
- **Behavior**: Connects to the `/` namespace. Implements auto-reconnection and specifically handles the `invalid_csrf` error by fetching a new token and forcing an underlying Engine.IO reconnect to inject the new cookie.

### `session-manager.js` (Lifecycle Orchestration)

- **Contract**: The most complex core module. It coordinates the high-level lifecycle of backend sessions.
- **Behavior**:
  - `fetchSessions()`: Polls the backend for active local and remote sessions, parsing the results.
  - `renderLauncher()`: Transforms the fetched session data into the HTML structures for the connection screen.
  - Handles session termination, reclamation, and updates to the `HostStateManager`.

### `pwa-system.js` (Browser Integration)

- **Contract**: Handles interactions with native browser APIs.
- **Behavior**: Manages the Screen Wake Lock API to prevent the device from sleeping during active sessions. Handles dynamic page title updates and the custom PWA "Install App" banner logic.

## Internal Dependencies

- Modules within `core` heavily cross-reference each other (e.g., `session-manager` relies on `api.js` and `socket.js`).

## External Dependencies

- **`src/static/js/ui/*`**: The UI layer consumes `globalState` and the networking utilities.
- **`src/static/js/terminal/ui.js`**: Relies on `socket.js` and `api.js` for establishing individual PTY connections.
- **`src/static/main.js`**: Wires the `EventBus` and core initialization logic.
