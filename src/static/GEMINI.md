# src/static Module

## Purpose
This directory contains all the frontend assets for the Gemini WebUI. This includes the monolithic `app.js` which manages the Xterm.js terminal instances and SocketIO connections, styles (`base.css`, `mobile.css`), and PWA manifests. 

## Internal Dependencies
- Uses `openapi.yaml` for API definitions.
- Depends on external CDNs or bundled node_modules (via HTML templates) for libraries like Xterm.js and Socket.IO.

## External Dependencies
- Served directly by the Flask application to the client's browser.
- Relied upon by `src/templates/index.html` to provide the interactive behavior and styling.