# Internal API Documentation

This document describes the internal communication interfaces between the Gemini WebUI frontend (`src/static/app.js`) and the Flask/Socket.IO backend.

## 1. REST APIs (Flask)

All internal REST APIs are prefixed with `/api/` and require a valid session (and CSRF token for mutating requests).

### Configuration & Settings

- **`GET /api/config`**: Retrieves the current application configuration.
- **`POST /api/config`**: Updates the application configuration.

### API Keys Management

- **`GET /api/management/api-keys`**: Lists all active programmatic access tokens.
- **`POST /api/management/api-keys`**: Creates a new access token.
- **`DELETE /api/management/api-keys/<id>`**: Revokes a specific access token.

### Session Management

- **`GET /api/sessions/persisted`**: Retrieves the state of persisted tabs for UI restoration.
- **`POST /api/migrate-tabs`**: Updates the order or state of persisted tabs.
- **`GET /api/management/sessions`**: Lists all active processes managed by the backend.
- **`DELETE /api/management/sessions/<pid>`**: Force-terminates a specific active process.
- **`GET /api/sessions`**: Lists available Gemini sessions (via `gemini -l`).

### Hosts & SSH Keys

- **`GET /api/hosts`**: Lists all configured SSH target hosts.
- **`POST /api/hosts`**: Adds or updates an SSH host configuration.
- **`DELETE /api/hosts/<host_id>`**: Removes an SSH host.
- **`POST /api/hosts/reorder`**: Updates the display order of hosts.
- **`GET /api/keys`**: Lists available SSH private/public keys.
- **`POST /api/keys`**: Uploads a new SSH key pair.
- **`DELETE /api/keys/<key_name>`**: Deletes a specific SSH key.
- **`POST /api/keys/<key_name>/rotate`**: Rotates the specified instance key.

### File Operations

- **`POST /api/upload`**: Uploads a file to the server workspace.
- **`GET /api/download/<filename>`**: Downloads a file from the server workspace.

### Prompts

- **`GET /api/prompts`**: Retrieves all saved command snippets.
- **`POST /api/prompts`**: Creates or updates a saved prompt.
- **`DELETE /api/prompts/<prompt_id>`**: Deletes a saved prompt.

### Shares (Terminal Snapshots)

- **`GET /api/shares`**: Lists all created terminal snapshots.
- **`POST /api/shares`**: Creates a new snapshot from the current terminal state.
- **`DELETE /api/shares/<share_id>`**: Deletes a snapshot.
- **`GET /s/<share_id>`**: (UI Route) Renders the read-only snapshot viewer.

### Utilities

- **`GET /api/csrf-token`**: Retrieves a CSRF token required for `POST`/`DELETE` requests.
- **`GET /api/health`**: Simple health check endpoint.

---

## 2. WebSocket Events (Socket.IO)

The core terminal interaction is driven by bidirectional WebSocket events via Socket.IO.

### Client-to-Server (Frontend -> Backend)

These events are emitted by `src/static/app.js`:

- **`join_room`**
  - **Payload**: `{ room: "<tab_id>" }`
  - **Purpose**: Subscribes the client to output streams for a specific terminal tab.
- **`pty-input`**
  - **Payload**: `{ input: "<keystrokes>", session_id: "<tab_id>" }`
  - **Purpose**: Sends user input (keystrokes, commands) to the pseudo-terminal.
- **`pty-resize`**
  - **Payload**: `{ rows: <int>, cols: <int>, session_id: "<tab_id>" }`
  - **Purpose**: Updates the terminal dimensions on the backend to match the frontend UI.
- **`terminate_session`**
  - **Payload**: `{ session_id: "<tab_id>" }`
  - **Purpose**: Force-kills the underlying process associated with the tab.

### Server-to-Client (Backend -> Frontend)

These events are listened for by `src/static/app.js`:

- **`pty-output`**
  - **Payload**: `{ output: "<ansi_text>", session_id: "<tab_id>" }`
  - **Purpose**: Streams process `stdout`/`stderr` to be rendered by Xterm.js.
- **`sync-tabs`**
  - **Payload**: `[ { tab_id: "...", title: "..." }, ... ]`
  - **Purpose**: Triggers a UI refresh to match the backend's persisted tab state.
- **`session-terminated`**
  - **Payload**: `{ session_id: "<tab_id>" }`
  - **Purpose**: Notifies the UI that a backend process has exited, prompting the UI to close the corresponding tab.
- **`error`**
  - **Payload**: `{ message: "<error_details>" }`
  - **Purpose**: Generic error reporting for UI flash messages or console logging.
