# src/gateways Module

## Purpose

The `src/gateways` directory serves as the real-time communication backbone of the Gemini WebUI. It is responsible for bridging the browser-based client (primarily Xterm.js via Socket.IO) with the server-side infrastructure (PTYs, process management, and background polling). It manages the entire lifecycle of terminal sessions over WebSockets, handling connections, disconnections, data streaming, window resizing, and session reclamation.

## General Themes

- **Real-Time Event Handling**: Everything in this module revolves around Socket.IO events (`@socketio.on`). It defines the contract for bidirectional communication.
- **Concurrency & Throttling**: Uses `eventlet` for greenlet-based concurrency. Dedicated reader threads stream output from PTYs to clients. It implements precise throttling (e.g., `socketio.sleep()`) and burst-mode chunking (`is_burst`, `burst_end`) to ensure smooth browser rendering without overwhelming the event loop.
- **Session Persistence & Reclamation**: Supports reclaiming orphaned or detached sessions. This allows users to refresh the page or reconnect from a different device without losing their terminal state, handling the complex logic of re-streaming scrollback buffers.
- **Background Orchestration**: Manages continuous background polling (`background_session_preloader`) to monitor external hosts for active sessions, updating internal caches and broadcasting status changes to connected clients.
- **Strict Separation of Concerns**: Isolates real-time "gateway" logic from traditional REST HTTP routes (`src/routes`) and core business logic/process management (`src/infrastructure`, `src/services`).

## Module Contracts & APIs

### `terminal_socket.py`

This is the primary module governing all WebSocket interactions.

- **Connection Management**

  - `handle_connect()`: Validates CSRF tokens upon connection and establishes the initial handshake.
  - `handle_disconnect()`: Cleans up internal tracking when a client disconnects, ensuring background processes are correctly managed or left orphaned for later reclamation.
  - `on_join_room()`: Subscribes a client to a specific terminal session room.

- **Session Lifecycle**

  - `pty_restart()` / `start_session()`: Handles requests to spawn new PTY sessions or attach to existing ones. Parses parameters like `ssh_target`, `ssh_dir`, and `resume` to determine how the session should be initialized via the `process_manager`.
  - `on_terminate_session()`: Handles explicit requests from the client to kill a PTY process.

- **Data I/O**

  - `pty_input()`: Receives keystrokes or pasted text from the client and writes it to the underlying PTY file descriptor.
  - `pty_resize()`: Receives terminal dimension changes (rows/cols) and resizes the underlying PTY to match the browser's viewport.
  - `session_output_reader()` (Background Task): A dedicated greenlet spawned for each active session. Continuously reads from the PTY and emits `pty-output` events to the connected client room. Implements logic to handle large bursts of data gracefully.

- **Dashboard & Monitoring**
  - `background_session_preloader()`: A long-running task that periodically queries configured hosts (via `session_manager.fetch_remote_sessions`) to maintain an up-to-date cache of active instances.
  - `handle_get_sessions()` / `handle_get_management_sessions()`: Responds to client requests for the list of available sessions, returning data from the cache populated by the preloader.

## Internal Dependencies

- **`src/extensions.py`**: Imports the configured `socketio` instance.
- **`src/services/session_manager.py`**: Relies on this for high-level session tracking, caching, and orchestration.
- **`src/infrastructure/process_manager.py`**: Relies on this for low-level PTY spawning, reading, writing, and signal handling.
- **`flask` / `flask_socketio`**: For session context and event routing.
- **`eventlet`**: For asynchronous task execution and sleeping.

## External Dependencies

- **`src/static/js/terminal/ui.js`**: The frontend Xterm.js implementation is the primary consumer of the events defined here (e.g., listening for `pty-output`, emitting `pty-input`).
- **`src/app.py`**: Imports and registers this module to attach the event handlers to the global application context.
