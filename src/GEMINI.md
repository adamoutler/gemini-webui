# src Module

## Purpose

The `src` directory serves as the core backend of the Gemini WebUI project. It is a well-structured set of managers handling specific domains: terminal emulation (`session_manager`, `process_manager`), security (`auth_ldap`), configuration (`config`), and data management (`prompt_manager`, `share_manager`). The `app.py` file acts as the primary hub, initializing these components and registering blueprints from the `routes` subdirectory. It handles the end-to-end terminal experience, from PTY management and SSH multiplexing to session persistence and sharing. It also includes LDAP authentication and specialized SQLite-backed managers for prompts and shares.

## Internal Dependencies

- **`src/routes/`**: The core logic depends on the blueprints for its interface.
- **`src/static/` and `src/templates/`**: Utilized for frontend assets and UI rendering.

## External Dependencies

- **Test Suite**: The entire test suite directly depends on the files in this directory for unit and E2E testing.
- **Containerization & CI**: The Dockerfile, Docker Compose configuration, and development/CI scripts depend directly on this directory to build and run the application.
