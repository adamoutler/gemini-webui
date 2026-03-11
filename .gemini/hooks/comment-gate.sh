#!/bin/bash
# .gemini/hooks/comment-gate.sh

# Read JSON payload from stdin
PAYLOAD=$(cat -)

# Extract tool arguments using jq
COMMENT=$(echo "$PAYLOAD" | jq -r '.tool_input.comment_html // empty')
TICKET_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.work_item_id // empty')
PROJECT_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.project_id // empty')

# Rule 2 & 3: Validate commits via reality-checker when a hash is provided in a comment
if [[ -n "$COMMENT" && "$COMMENT" != "null" ]]; then
  # Regex extract a likely commit hash (at least 7 hex chars)
  COMMIT_HASH=$(echo "$COMMENT" | grep -oE '\b[0-9a-f]{7,40}\b' | head -n 1)
  
  if [[ -n "$COMMIT_HASH" ]]; then
    # Trigger reality-checker agent for strict validation
    # Use standard terminal commands. Assuming gemini is installed globally or in path.
    # We output to stderr to prevent it from messing up the JSON output for the hook
    >&2 echo "Triggering reality-checker for commit: $COMMIT_HASH on ticket $TICKET_ID"
    
    # We run the reality-checker. It must return 'PASS' somewhere in its response to succeed.
    VERDICT=$(gemini run --agent testing-reality-checker "Verify if commit $COMMIT_HASH successfully implements the requirements for ticket $TICKET_ID. Reply strictly with 'PASS' or 'FAIL: <reason>'.")
    
    if [[ "$VERDICT" == *"PASS"* ]]; then
        # The comment is allowed. We can optionally close the ticket here or rely on CI.
        # Let's echo allow and let the hook pass.
        echo '{"decision": "allow"}'
        exit 0
    else
        # Escape quotes in verdict for JSON string
        CLEAN_VERDICT=$(echo "$VERDICT" | sed 's/"/\\"/g' | tr '\n' ' ')
        echo "{\"decision\": \"deny\", \"reason\": \"Reality-checker validation failed for commit $COMMIT_HASH. Feedback: $CLEAN_VERDICT\"}"
        exit 0
    fi
  else
      # If there is no commit hash, we might want to deny it if it's meant to close the ticket,
      # but generally, users/agents can leave regular comments.
      echo '{"decision": "allow"}'
      exit 0
  fi
fi

# Default allow for benign updates
echo '{"decision": "allow"}'
