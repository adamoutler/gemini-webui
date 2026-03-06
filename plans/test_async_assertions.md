# Improve assertions in test_async.py and test_upload_download.py

## Details of what's required
Both `test_async.py` and `test_upload_download.py` have PTY/SSH mock tests that verify that a subprocess or session is added, but fail to deeply verify the exact state or the commands sent to the PTY.
- In `test_async.py`, `test_pty_restart_basic` (and other similar tests) heavily rely on mocks but don't verify the final state of the session object as thoroughly as they could (e.g., checking default values for rows/cols if not provided or the specific process states). Update these tests to assert the exact state of the process, PTY fd, and session metadata.
- In `test_upload_download.py` (and potentially others), ensure that SSH command assertions verify the exact command string format including shell escaping, quoting, and arguments, rather than just asserting that the mock was called. Ensure we verify environment variables being passed down correctly.

## Test recommendations
- Assert against `mock.call_args` to ensure specific shell commands, paths, and environment variables are being passed precisely.
- Run `pytest tests/test_async.py tests/test_upload_download.py` to ensure passing tests.
- Verify test coverage using `pytest --cov=src` to see if there are missing execution paths in these async functions.

## Definition of Done
- Mock verifications check the full command strings, paths, and arguments rigorously instead of just checking if a mock was called.
- Session object state (rows, cols, fd, etc.) is fully verified after initialization in async PTY tests.
- Tests pass locally.