---
name: git-commit
description: Guide for committing changes. Use this when the user asks you to commit code or wrap up a PR.
---

# Git Commit workflow

When asked to commit code, you MUST follow these steps:

1.  **Ticket Tracking**: Ensure the identifier for the current Kanban ticket you are working on (e.g., `GEMWE-123`) is saved to the file `/tmp/gemini-webui-ticket.txt`.
    *   If you don't know the current ticket identifier, use MCP tools like `list_projects` and `list_work_items` or ask the user.
    *   Write it to the file: `echo "GEMWE-123" > /tmp/gemini-webui-ticket.txt`
2.  **Commit Changes**: Use standard `git add <files>` and `git commit -m "<message>"`.
3.  **Pre-Commit Hook Awareness**: Be aware that the `pre-commit` hook will automatically:
    *   Run `pytest` to execute all tests.
    *   Pipe test results to the `reality-checker` agent.
    *   Wait for AI validation of your changes against the Kanban ticket requirements.
4.  **Handling Rejection**: If the commit is rejected (the pre-commit hook fails), read the output from the hook, particularly the contents of `/tmp/gemini-webui-reality-results.txt` which will explain why `reality-checker` rejected the changes (e.g., missing tests, incomplete features). Fix the issues and try committing again.
5.  **Successful Commit & Closure**: Once the commit succeeds (QA approved), you must:
    *   Add a comment to the Kanban ticket detailing the work done.
    *   Annotate the comment with the full Git commit URL (e.g., `https://git.adamoutler.com/aoutler/gemini-webui/commit/<hash>`).
    *   Move the ticket to the **Done** state. (You are forbidden from closing tickets without approval from the QA team triggered by the commit).
