# Ticket Closure — Mandatory Rules

## You CANNOT close tickets directly

You do **not** have `complete_work` or `transition_ticket` MCP tools.
The only way to transition a ticket to "Done" is through the QA gate script.

## Forbidden Actions

You MUST NEVER:

- Use `curl`, `wget`, or any HTTP client to interact with `kanban.hackedyour.info` to change ticket state
- Use the `gh` CLI to interact with the kanban system
- Attempt to bypass the QA gate by any means

## How to Close a Ticket

When you believe a work item is complete:

1. **Commit** — Ensure all code changes are committed (`git status --porcelain` must be empty)
2. **Push** — Ensure all commits are pushed to origin (`git push`)
3. **Wait for CI** — Wait for GitHub Actions to pass on the current HEAD
4. **Run the gate** — Execute: `./scripts/complete_work.sh TICKET-123`

The script handles everything:

- Verifies pre-flight conditions (clean repo, pushed, CI green)
- Invokes an **independent** `@reality-checker` agent (separate Gemini instance) to audit the work
- If READY → transitions the ticket to Done
- If NEEDS WORK → outputs feedback for you to act on

## If the Script Rejects

- **Read the output carefully** — it tells you exactly what to fix
- Address the feedback from the reality checker
- Re-run `./scripts/complete_work.sh TICKET-123`
- The reality checker defaults to "NEEDS WORK" — you need overwhelming evidence of completion

## Posting Evidence Before Closure

Before running `complete_work.sh`, ensure the ticket has:

- A comment with the commit hash of the completed work
- References to any screenshots in `public/qa-screenshots/` if applicable
- Notes on what tests were added or passed

The reality checker reads the ticket comments as evidence. More proof = higher chance of approval.
