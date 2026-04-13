# src/templates Module

## Purpose
Contains the Jinja2 HTML templates used by the Flask application to render the initial UI shell before JavaScript takes over.

## Internal Dependencies
- Links to assets in `src/static/` (CSS, JS, icons).

## External Dependencies
- Rendered by `src/routes/ui.py` and `src/app.py` when serving the main application or specific views like the sharing interface (`share.html`).