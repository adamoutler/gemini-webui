# Bug Fix: Ensure highest resume number is used for new sessions

**Details:**
When creating a new session, the system needs to intelligently assign the `resume` session number (e.g., `-r 1`, `-r 2`).
Currently, there might be a race condition or logic flaw where the next session number isn't reliably assigned the highest available number + 1. If multiple sessions are created or if the page is refreshed, it should pick the newest available one or correctly increment.

Logic to update:
- When a user clicks "+ New", the backend or frontend should query the existing sessions (either via the Gemini CLI state or internal tracking).
- If resuming an existing session, it should prioritize the most recently active one.
- If creating a completely new session alongside existing ones, it should allocate the `MAX(existing_numbers) + 1`.

**Test Recommendations:**
1. Unit test (`tests/test_session_management.py` or similar) that creates 3 sessions, disconnects, and verifies the next "+ New" action assigns the correct `-r <N>` argument.
2. Verify the behavior handles cases where session numbers are non-sequential (e.g., 1, 3 -> next should be 4).

**Definition of Done:**
- New terminal sessions always receive a correct, non-colliding resume number that follows the highest existing number.
- No two tabs will inadvertently resume the exact same session file unless explicitly intended.