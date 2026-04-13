# src Module

## Purpose
This directory contains the core backend logic for the Gemini WebUI application, which is built using Flask and SocketIO. It handles session management, SSH multiplexing, configuration, and shared application state.

## Internal Dependencies (What this module uses)
- `src/routes/`: For defining REST APIs and UI endpoints.
- `src/static/`: For serving the frontend UI (Xterm.js, SocketIO client).
- `src/templates/`: For rendering the base HTML shells.

## External Dependencies (What depends on this module)
- `tests/`: The test suite relies on these core components (e.g., `app.py`, `session_manager.py`) for both unit and end-to-end testing.