# tests/proof Module

## Purpose

The `tests/proof` directory is a dedicated storage for empirical verification scripts used to generate 'proof' of functionality and bug fixes. These scripts, mostly written in Python using Playwright and subprocess orchestration, interact with a live instance of the application to capture screenshots, DOM dumps, and diagnostic reports. They are primarily used by QA and automated agents (like @reality-checker) to verify that the 'Definition of Done' for specific project tasks (often tied to Kanban ticket IDs) has been met.

## Internal Dependencies

- **`src/` module**: Depends on the core application logic to serve the UI and API for testing.
- **Python libraries**: Playwright, subprocess, shutil, etc., for browser automation and artifact management.

## External Dependencies

- **QA and Automated Agents**: Used heavily by `@reality-checker` and QA processes.
- **Documentation**: Produces artifacts that are stored in documentation and public static directories (`docs/qa-images/`, `public/qa-screenshots/`).
