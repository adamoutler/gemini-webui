# tests/mock Module

## Purpose

The `tests/mock` directory contains a Python-based mock of the Gemini CLI (`gemini`). It is designed to simulate terminal interactions, session management, and state persistence for automated testing without requiring the actual Gemini CLI. It is widely used across the test suite via the `server` fixture in `tests/conftest.py` and specifically in E2E and regression tests.

## Internal Dependencies

- **Standard Libraries**: Uses standard Python libraries to simulate interactions.
- **Project Environment Variables**: Relies on project-specific environment variables like `DATA_DIR` to manage state and persistence correctly within the mocked environment.

## External Dependencies

- **`tests/conftest.py`**: Injects this mock directory into the PATH for the test server fixture.
- **Test Suites**: E2E and regression tests (e.g., `tests/e2e/test_e2e_resume_regression.py`, `tests/reproduce_zombie_v2.py`) depend on this mock to verify session resumption and state persistence without needing a real backend environment.
