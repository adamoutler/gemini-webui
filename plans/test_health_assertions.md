# Improve assertions in test_health_indicators.py

## Details of what's required
The `test_health_indicators.py` currently tests visual representations by checking for emoji text matches (e.g., asserting that "🟢" or similar emojis appear in the output). 
While functional, relying solely on text matches for emojis makes the tests brittle and misses verifying the internal DOM state.
- Update `test_connection_health_indicators` (and any related health checks) to inspect the underlying data attributes, classes, or IDs. For example, if an element has a class like `.status-connected` or a data attribute `data-status="ok"`, assert against those rather than (or in addition to) the emoji characters.
- Ensure that the UI state strictly matches the expected internal model state during different health phases (connected, disconnected, error).

## Test recommendations
- Use BeautifulSoup or Playwright (whichever is used in these tests) to parse the HTML and assert on classes/attributes.
- Ensure that multiple states (e.g., green, yellow, red or online/offline/degraded) are checked for both visual output and DOM state.
- Run `pytest tests/test_health_indicators.py` to confirm the tests pass reliably.

## Definition of Done
- Health indicator assertions check the underlying CSS classes and/or data attributes, not just the raw text of emojis.
- The tests are more resilient to pure visual/typographical changes.
- `pytest tests/test_health_indicators.py` passes successfully.