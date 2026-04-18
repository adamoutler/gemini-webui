# tests/unit Module

## Purpose

This directory contains a high-density suite of unit and low-level integration tests that serve as the primary quality gate for the `gemini-webui` project. These tests validate the isolated functionality of core backend components, enforce security mandates, and ensure the stability of interactive UI elements. Key areas of testing include:

- **Backend Core Logic**: Rigorous verification of the `SessionManager`, `ProcessManager`, and SSH multiplexing logic.
- **REST API Endpoints**: Comprehensive testing of the application's REST interface, including host lifecycle management, CSRF token generation, and health checks.
- **Security Mandates**: Automated validation of defenses against common vulnerabilities such as ANSI injection, Broken Object-Level Authorization (BOLA), and Cross-Site Request Forgery (CSRF).
- **Interactive UI Testing**: Lightweight browser-based testing using Playwright to verify xterm.js terminal instances, flash messages, and responsive layouts directly against a running application instance.
- **Authentication & Authorization**: Testing LDAP input sanitization and mock authentication flows to ensure secure access control.
- **Utility and Asynchronous logic**: Verification of internal helper methods for file I/O, asynchronous task management, and result caching.

## Internal Dependencies

- **`src/` module**: The tests directly import and execute code from the core application, specifically `app.py`, `session_manager.py`, `process_manager.py`, `utils.py`, `auth_ldap.py`, and `share_manager.py`.
- **`tests/conftest.py`**: Provides the foundational pytest infrastructure, including the `server` fixture (which spawns a test-scoped Flask instance), `test_data_dir` for isolated filesystem tests, and common API client configurations.
- **`tests/mock/`**: Supplies mock binaries (e.g., `gemini` mock) and environment simulations to isolate tests from host-specific system dependencies.
- **`src/static/` and `src/templates/`**: The Playwright-based tests (`test_ui.py`, etc.) implicitly depend on the frontend assets (HTML, CSS, JS) to render the UI for functional validation.
- **Python libraries**: Relies on `pytest` for test orchestration, `playwright` for browser automation, and standard libraries like `unittest.mock`, `json`, and `os`.

## External Dependencies

- **CI/CD Pipeline**: Integrated into the project's GitHub Actions and Jenkins (`Jenkinsfile`) pipelines as a mandatory block; all unit tests must pass for a build to be considered successful.
- **Development Workflow**: Utilized by developers and automated agents (like `TestingRealityChecker`) to verify the integrity and security of features before they are merged.
- **Test Reporting**: Generates JUnit XML artifacts (`results.xml`) and detailed log outputs used for long-term health tracking and debugging within Jenkins and GitHub.
- **Development Environment**: Requires a properly initialized virtual environment (`setup_dev.sh`) and Playwright browser binaries to execute the full suite.
