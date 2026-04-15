# src/templates Module

## Purpose

This directory contains the Jinja2 HTML templates used to render the frontend user interface of the application. This includes:

- `index.html`: The primary UI shell, which hosts the terminal environment, navigation, settings, and functional modals.
- `share.html`: A specialized viewer for terminal session snapshots created via the sharing feature.
- `test_launcher.html`: A debugging interface used for starting ephemeral test sessions.

## Internal Dependencies

- **Static Assets**: Links to CSS, JavaScript, and image resources located in `src/static/` (e.g., `base.css`, `app.js`, `favicon.svg`).
- **Jinja2 Context Variables**: Expects dynamic variables from Flask routes, such as `csrf_token`, `version`, `session_name`, `theme`, and `html_content`.

## External Dependencies

- **`src/routes/ui.py`**: The primary router that renders the main application shell and test utility.
- **`src/routes/shares.py`**: Renders the viewer for shared session snapshots.
- **`src/app.py`**: Initializes the Flask application, sets up CSRF protection (`CSRFProtect`), and registers the blueprints that utilize these templates.
