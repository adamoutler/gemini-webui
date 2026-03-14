# Timeout Standards and Guidelines

Timeouts are strictly enforced in this project to prevent CI/CD lockups and agent hanging during development. You are highly encouraged to use multiple layers of timeouts to ensure robust and fast failure.

## 1. Pytest Timeout Annotation (Primary Method)
Always use the `pytest-timeout` plugin to enforce a strict upper bound on test execution time. This prevents hanging tests from blocking the entire suite.

```python
import pytest

@pytest.mark.timeout(10) # Fails the test if it takes longer than 10 seconds
def test_example():
    # test logic
    pass
```
*Note: We have also configured `addopts = --timeout=60` in `pytest.ini` as a global fallback, but explicit `@pytest.mark.timeout` annotations are preferred for granular control.*

## 2. Linux `timeout` Command (Secondary / Wrapper Method)
When executing tests locally or in scripts (especially AI agents running shell commands), always wrap the execution with the Linux `timeout` utility. This acts as an absolute fail-safe if the Python process itself hangs irrecoverably.

```bash
time timeout 30 pytest tests/test_file.py
```

## 3. Playwright/Async Timeouts (Granular Control)
For UI and end-to-end tests, specify explicit timeouts on page operations to fail fast when UI elements do not appear.

```python
# Fail fast if element is not found within 5000ms
page.wait_for_selector(".my-element", timeout=5000)
```

## Validation
See `tests/test_timeout_validation.py` for a dedicated example demonstrating these timeout methods in action.
