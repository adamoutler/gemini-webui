# src/routes Module

## Purpose

The `src/routes` module is the primary interface layer for the Gemini WebUI application, separating UI rendering, management APIs, programmatic integrations, and terminal lifecycle logic into dedicated files. It isolates concerns like SSH host management (`host_keys.py`), session sharing (`shares.py`), and interactive terminal control (`terminal.py`). `api.py` acts as the backbone for the frontend, handling everything from settings synchronization to file uploads.

## Internal Dependencies

- **`src.app`**: All route modules depend heavily on the main app for shared state (SocketIO, logging) and authentication decorators.
- **`src.session_manager` and `src.process_manager`**: Relied upon for the heavy lifting of terminal and SSH orchestration.
- **`src.prompt_manager` and `src.shared_state`**: Used for data management and state sharing across routes.

## External Dependencies

- **Frontend / Client**: The client-side application heavily depends on these routes to function.
- **`src/app.py`**: The main application file registers the blueprints from `src/routes` to expose the endpoints.
