# src/templates Module

## Purpose

The `src/templates` directory contains the Jinja2 HTML templates used to render the application. It acts as the structural foundation for the Single Page Application (SPA), the Progressive Web App (PWA) shell, and standalone pages (like shared sessions). It strictly separates structure (HTML) from presentation (CSS) and behavior (JS).

## General Themes

- **Modular Partials**: The UI is broken down into small, highly cohesive partial templates (`partials/`) and modals (`partials/modals/`). This prevents a massive, unmaintainable `index.html` file.
- **Declarative Event Binding**: To maintain a strict Content Security Policy (CSP) and avoid inline JavaScript, the project uses a custom event delegation system. HTML elements use `data-onclick`, `data-onchange`, and `data-cmd` attributes instead of standard `onclick`. These are parsed and executed by global listeners in the JS layer.
- **Dynamic Placeholders**: Many partials (like `tab_bar.html` and `terminal_container.html`) contain minimal static HTML. They serve primarily as `div` anchors where the frontend JavaScript modules (like `src/static/js/ui/tabs.js`) will dynamically inject content.
- **PWA Readiness**: The `index.html` template includes specific `<meta>` tags for viewport scaling, theme colors, and Apple-specific web app capabilities to ensure a native-like experience on mobile devices.

## Module Contracts & APIs

### `index.html` (The Shell)

- **Contract**: The primary entry point for the Gemini WebUI.
- **Behavior**: It aggregates all partials using Jinja2 `{% include %}` statements. It establishes the global layout grid (sidebar, main content area, modals) and loads all essential CSS and JS assets.

### `share.html` (Standalone Page)

- **Contract**: Renders a read-only snapshot of a terminal session.
- **Behavior**: Expects specific Jinja2 variables (`session_name`, `theme`, `html_content`) passed from the backend `src/routes/shares.py`. It is a standalone page that does not load the full SPA logic.

### `partials/`

- **`sidebar.html`**: The main navigation menu.
- **`launcher.html`**: The connection screen where users select hosts or enter quick-connect commands.
- **`tab_bar.html` & `terminal_container.html`**: The placeholders for the active terminal sessions.
- **`mobile_controls.html`**: Specialized on-screen modifier keys (Ctrl, Alt, Tab, Esc) visible only on mobile viewports. It heavily uses `data-cmd` and `data-func-adjust` attributes.

### `partials/modals/`

- **Contract**: Each file represents a discrete popup dialog. They are all included in `index.html` but remain hidden (`display: none`) until triggered by the JS UI layer.
- **Key Modals**: `settings_modal.html` (Host/Key config), `file_transfer_modal.html`, `automation_dashboard.html`, `share_modal.html`.

## Internal Dependencies

- **Jinja2 Environment**: Relies on the global template context provided by `src/app.py` (e.g., `version`, `csrf_token()`).

## External Dependencies

- **`src/static/main.js`**: The `executeDataAction` function here is the sole consumer and executor of the `data-onclick` and `data-onchange` strings defined in these templates.
- **`src/static/js/mobile/mobile-input-extra.js`**: Consumes the `data-cmd` attributes from the mobile controls partial.
