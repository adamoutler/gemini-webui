# src/routes Module

## Purpose

The `src/routes` directory serves as the application's interface layer. It is organized into functional blueprints that define the HTTP endpoints and their associated logic. This layer acts as the bridge between the HTTP requests (from the frontend UI or external API clients) and the core business logic encapsulated in `src/services`.

## General Themes

- **Blueprint Isolation**: The application's surface area is divided into logical blueprints (`api_bp`, `terminal_bp`, `external_api_bp`, etc.) to maintain separation of concerns.
- **Security by Default**: The vast majority of endpoints are protected by the `@authenticated_only` decorator, ensuring that only users with a valid session can interact with the system. Programmatic endpoints use `@api_key_required`.
- **Path Validation**: Operations involving file systems (`api.py`, `shares.py`) employ strict path resolution and validation to prevent directory traversal vulnerabilities (CodeQL mitigations).
- **Service Delegation**: Routes are designed to be thin controllers. They handle request validation, parameter extraction, and JSON response formatting, but delegate the heavy lifting to managers and services (e.g., `session_manager`, `TerminalService`).

## Module Contracts & APIs

### `api.py` (Internal API)

- **Contract**: Handles core system operations for the frontend UI.
- **Key Endpoints**:
  - `/api/config`: GET/POST for application configuration.
  - `/api/upload`, `/api/download`: Workspace file transfers with strict boundary checks.
  - `/api/tasks`: GET/DELETE for managing background processes.
  - `/api/system-logs`: Access to backend application logs.

### `terminal.py` (Session Lifecycle)

- **Contract**: Manages the persistence, reclamation, and termination of terminal sessions.
- **Key Endpoints**:
  - `/api/sessions/persisted`: Lists tabs saved in the user's browser storage.
  - `/api/sessions/migrate`: Handles complex logic for transferring session ownership or state.
  - `/api/sessions/<uuid>`: DELETE to forcefully terminate a specific PTY session.
  - `/api/files/search`: Supports the terminal's smart search feature.

### `host_keys.py` (Connectivity)

- **Contract**: Orchestrates target host definitions and SSH identity management.
- **Key Endpoints**:
  - `/api/hosts`: GET/POST/DELETE for the launcher's connection list.
  - `/api/ssh-keys`: GET/POST/DELETE for managing private keys.
  - `/api/rotate-key`: Rotates the instance's primary SSH key for improved security.

### `external_api.py` (Programmatic Access - API v1)

- **Contract**: Provides a versioned, strictly schema-validated API for external tools to interact with Gemini WebUI. Protected by API keys.
- **Key Endpoints**:
  - `/api/v1/sessions` (POST): Programmatically spawn new sessions or commands.
  - `/api/v1/hosts/states`: Query the status of known hosts.
  - `/api/v1/hosts/states/wait`: Long-polling endpoint to wait for specific host state changes.

### `automation.py` (Task Scheduling)

- **Contract**: Manages recurring task schedules and automation history.
- **Key Endpoints**:
  - `/api/automation/schedules`: CRUD operations for automation jobs.
  - `/api/automation/execute`: Manually trigger a scheduled job immediately.

### `ui.py` (Frontend Serving)

- **Contract**: Serves the Single Page Application (SPA) and Progressive Web App (PWA) assets. Unauthenticated by design (to serve the login page).

## Internal Dependencies

- **`src/decorators/validation.py`**: Used heavily for request validation (e.g., `@validate_json_schema`).
- **`src/services/*`**: Consumes services like `TerminalService`, `SessionManager`, and `ScheduleManager`.
- **`flask`**: Uses `Blueprint`, `request`, `jsonify`, `send_from_directory`.

## External Dependencies

- **Frontend Client**: The JavaScript in `src/static/js/` consumes these endpoints via `fetchWithCSRF()`.
- **External Clients**: Scripts or tools consume `/api/v1/*` using Bearer tokens.
