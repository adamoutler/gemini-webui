# tests/e2e Module

## Purpose

The `tests/e2e` directory serves as the comprehensive end-to-end testing suite for the Gemini WebUI project. It uniquely combines Python-based Playwright tests (for full-stack browser automation) and Node.js-based unit tests (for specialized frontend logic like mobile input handling). These tests verify the application's responsiveness, complex interactive features (e.g., sticky modifiers, terminal overlays), and core session workflows across different viewports. The suite is a mandatory part of the CI/CD pipeline and generates visual artifacts (screenshots) stored in `docs/qa-images/` as proof of work for QA validation.

## Internal Dependencies

- **`src.app`**: The Flask application itself.
- **`tests/conftest.py`**: Shared fixtures including server startup and mock directory setup.
- **`tests/mock/`**: Mock binaries used to simulate the Gemini CLI environment.
- **`tests/utils/playwright_mobile_utils.py`**: Helper functions for E2E tests.
- **`src/static/mobile_input.js`**: Frontend modules directly tested by JavaScript files within `tests/e2e`.

## External Dependencies

- **Playwright & Node.js**: External tools required to run browser automation and JS tests.
- **Jenkins / CI/CD Pipeline**: The Jenkins build environment depends on these tests passing (via `pytest tests/`) as a mandatory stage in the pipeline.
