# src/static Module

## Purpose

The `src/static` directory is the hub for all client-side logic and presentation in the Gemini WebUI. It provides the interactive terminal interface through `app.js` (core logic) and `mobile_input.js` (mobile-specific UX enhancements). It supports Progressive Web App (PWA) features via `manifest.json`, `sw.js` (Service Worker), and dedicated icons/styling. Additionally, it contains the `openapi.yaml` specification for the external REST API.

## Internal Dependencies

- **Backend APIs**: The code relies on the backend Flask application for REST APIs (`/api/*`), WebSocket communication (`socket.io`), and security (CSRF tokens).
- **External Libraries**: Depends on several external libraries (Xterm.js and its addons, Socket.IO client) typically served via CDNs.

## External Dependencies

- **`src/templates/index.html`**: The primary consumer which brings the assets together.
- **Backend Servers**: `src/app.py` and `src/docs_server.py` are responsible for serving these files.
- **E2E Test Suite**: `tests/e2e/` is heavily dependent on the behavior defined within these static files for validating the application's functionality.
