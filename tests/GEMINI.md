# tests Module

## Purpose
This module contains the comprehensive test suite for the Gemini WebUI application, covering unit tests, end-to-end (E2E) tests with Playwright, and mocks for external services. It enforces a strict quality gate.

## Internal Dependencies
- Imports extensively from `src/` to test internal logic (e.g., `src.session_manager`, `src.utils`).
- Uses `tests.conftest` for shared pytest fixtures.
- Uses `tests.mock` and `tests.utils` for helper functions and mock data during test execution.

## External Dependencies
- Relied upon by GitHub Actions (`.github/workflows/`) and local development scripts (`scripts/smoke-test.sh`) to verify code integrity before merges or deployments.