# src/static/js/ui Module

## Purpose

The `src/static/js/ui` directory contains the modular presentation and user interaction components of the Gemini WebUI frontend. It organizes the complex client-side logic into distinct functional domains, transitioning away from monolithic scripts. This module is responsible for rendering the UI, capturing user interactions, and delegating business logic to the `core` or `terminal` modules.

## General Themes

- **Event Delegation**: Embraces a unified event delegation system defined in `src/static/main.js`. UI elements use `data-onclick` and `data-onchange` attributes with stringified function calls. This pattern reduces the number of event listeners and simplifies dynamically generated DOM.
- **Centralized State**: Relies on `globalState` (from `core/state.js`) as the single source of truth for UI rendering, avoiding fragile DOM-based state tracking.
- **EventBus Communication**: Modules communicate asynchronously using the `EventBus`, allowing deep components (like modals or terminal plugins) to trigger UI updates without tight coupling.
- **Modular Refactoring**: This directory is the result of breaking down massive legacy files (`app.js`, `main.js`) into logical groupings (Settings, Tabs, Modals, Automation).

## Module Contracts & APIs

### `tabs.js`

- **Contract**: Manages the lifecycle, rendering, and persistence of the multi-tab terminal interface.
- **Behavior**:
  - Loads saved tabs from browser local storage or synchronizes them with the backend session state.
  - Handles tab switching, renaming, and closing, including the complex "migration" logic when a session is transferred.
  - Provides the custom tab context menu.

### `settings.js`

- **Contract**: Manages application-wide configuration, target hosts, and SSH keys.
- **Behavior**:
  - `EnvVarManager`: Specialized handler for defining and injecting environment variables into terminal sessions.
  - Fetches and populates forms for adding/editing hosts and uploading private keys.
  - Provides Import/Export functionality for user settings.

### `modals.js`

- **Contract**: Encapsulates isolated popup interfaces for distinct tasks.
- **Behavior**:
  - Manages File Transfer (`uploadWorkspaceFile`, `downloadWorkspaceFile`).
  - Manages Image Pasting and Prompts (Snippets).
  - Manages the "Share Session" interface and "Task Monitor".

### `automation.js`

- **Contract**: The frontend interface for the scheduling subsystem.
- **Behavior**: Renders the automation dashboard, allowing users to define cron schedules, target hosts, and commands, and view execution history.

### `contextMenu.js`

- **Contract**: Provides a unified, custom right-click context menu for desktop users.
- **Behavior**: Bypasses the native browser context menu within terminal areas to provide application-specific actions (like customized copy/paste rules).

### `launcher.js` & `quick-connect.js`

- **Contract**: Manages the connection entry points.
- **Behavior**: `HostStateManager` tracks and updates visual health indicators for remote servers. `quick-connect.js` provides parsing logic for rapid SSH string entry.

### `theme.js`

- **Contract**: Manages the visual styling of the terminal and application.
- **Behavior**: Syncs the xterm.js theme with the application's overall CSS theme and handles font sizing.

## Internal Dependencies

- **`src/static/js/core/*`**: Relies heavily on `state.js` for data, `api.js` for CSRF-protected communication, and `event-bus.js` for dispatching actions.
- **`src/static/main.js`**: Functions must be registered in the `Actions` map here to be accessible via the `data-onclick` HTML attributes.

## External Dependencies

- **`src/templates/*.html`**: The HTML structure expects the functions defined in this module to be available when elements are interacted with.
