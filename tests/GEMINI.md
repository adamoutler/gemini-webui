# tests Module

## Purpose

The root of the `tests` directory acts as the foundational orchestration layer for the project's testing suite. It primarily provides shared fixtures (via `conftest.py`) for server and session management, baseline health/timeout tests (`test_timeout_validation.py`), and standalone reproduction scripts for debugging complex process-management and zombie issues (e.g., `reproduce_zombie_v2.py`). It establishes the testing context for all sub-directories.

**CRITICAL WARNING:** This project has a history of unit tests accidentally killing the host machine's SSH connection by targeting process groups with `os.killpg`. **You MUST read `tests/PROCESS_ISOLATION_AND_KILLING.md` before making any changes to process lifecycle management, process mocking, or test teardown logic.**

## Internal Dependencies

- **`src.app`**: Depends heavily on the main application factory for initialization.
- **`tests/mock/`**: Relies on mock environments and binaries for simulating terminal interactions.
- **Python Libraries**: Uses `pytest`, `eventlet`, and `playwright` for infrastructure and debugging scripts.

## External Dependencies

- **Sub-test Modules**: All subdirectories (`unit`, `e2e`, `proof`) depend on the shared fixtures and utilities provided by the root `conftest.py`.
- **CI/CD Pipelines**: Jenkins and GitHub Actions depend on this root infrastructure to execute their automated checks.
