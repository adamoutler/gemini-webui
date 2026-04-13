# src/routes Module

## Purpose
This module contains the routing definitions for the Flask application. It cleanly separates the REST API endpoints (`api.py`), external integrations (`external_api.py`), UI rendering routes (`ui.py`), terminal connection logic (`terminal.py`), host key management (`host_keys.py`), and file sharing (`shares.py`).

## Internal Dependencies
- Relies heavily on `src.session_manager`, `src.config`, and `src.process_manager` to execute the business logic requested by the endpoints.
- Uses `src.auth_ldap` for authentication where required.

## External Dependencies
- `src/app.py`: The main Flask application imports these blueprints to register the routes.