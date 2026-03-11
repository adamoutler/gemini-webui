#!/bin/bash
# .gemini/hooks/qa-gate.sh

PAYLOAD=$(cat -)

# Extract core metadata to validate assumptions
SESSION_ID=$(echo "$PAYLOAD" | jq -r '.session_id // empty')
MCP_CONTEXT=$(echo "$PAYLOAD" | jq -c '.mcp_context // empty')
SERVER_NAME=$(echo "$PAYLOAD" | jq -r '.mcp_context.server_name // empty')
TOOL_NAME=$(echo "$PAYLOAD" | jq -r '.mcp_context.tool_name // empty')

# Validation: ensure this is a valid payload containing the necessary metadata (existence check)
if [[ -z "$SESSION_ID" || -z "$MCP_CONTEXT" ]]; then
  # Not a recognized hook payload or missing context, allow it to proceed normally
  echo '{"decision": "allow"}'
  exit 0
fi

# Ensure we are operating strictly within the "kanban" MCP server context
if [[ "$SERVER_NAME" != "kanban" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# Unconditionally block the deletion of any work item
if [[ "$TOOL_NAME" == "delete_work_item" ]]; then
  jq -c -n --arg reason "Deleting kanban work items is strictly forbidden." '{"decision": "deny", "reason": $reason}'
  exit 0
fi

# Only apply the validation gate if the tool is explicitly 'update_work_item'
if [[ "$TOOL_NAME" == "update_work_item" ]]; then
  STATE=$(echo "$PAYLOAD" | jq -r '.tool_input.state // empty')
  WORK_ITEM_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.work_item_id // empty')
  PROJECT_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.project_id // empty')
  
  # Fetch the actual "Done" state UUID dynamically
  DONE_STATE_ID=$(curl -s "https://kanban.hackedyour.info/api/v1/workspaces/gemwebui/projects/${PROJECT_ID}/states/" \
    -H "x-api-key: ${KANBAN_API_KEY}" | jq -r '.results[] | select(.name == "Done") | .id')

  # Block direct updates to the "Done" state
  if [[ "$STATE" == "$DONE_STATE_ID" ]] || [[ "$STATE" == *"Done"* ]]; then
    mkdir -p /tmp/proof-gemini-webui
    rm -f /tmp/proof-gemini-webui/latest-test-results /tmp/proof-gemini-webui/primary_work_item_reference.json /tmp/proof-gemini-webui/changed_files.diff

    # Get the latest test results (from /tmp log files where the developer agents should output)
    cat << INNER_EOF > /tmp/proof-gemini-webui/latest-test-results
---
file: /tmp/proof-gemini-webui/latest-test-results
name: unit test results
description: the previous unit test results
---
$(find /tmp -maxdepth 1 -name "*test*.log" -o -name "*pytest*.log" -type f -exec cat {} + 2>/dev/null | tail -n 1000 || echo "No test logs found in /tmp. Developers must redirect test output to a .log file in /tmp.")
INNER_EOF

    # Get the git diff to show the files changed
    cat << INNER_EOF > /tmp/proof-gemini-webui/changed_files.diff
---
file: /tmp/proof-gemini-webui/changed_files.diff
name: Changed files diff
description: The current working directory changes and the latest commit
---
=== Uncommitted Changes ===
$(git diff HEAD 2>/dev/null || echo "No git repo or no uncommitted changes.")

=== Last Commits ===
$(git log -5 --stat --patch 2>/dev/null || echo "No commits found.")
INNER_EOF

    # Fetch the ticket directly from the Plane API
    cat << INNER_EOF > /tmp/proof-gemini-webui/primary_work_item_reference.json
---
file: /tmp/proof-gemini-webui/primary_work_item_reference.json
name: The primary work item.
description: Reality Checker is to make all judgement calls based on the content of this kanban ticket
---
INNER_EOF
    
    curl -s "https://kanban.hackedyour.info/api/v1/workspaces/gemwebui/projects/${PROJECT_ID}/issues/${WORK_ITEM_ID}/" \
      -H "x-api-key: ${KANBAN_API_KEY}" >> /tmp/proof-gemini-webui/primary_work_item_reference.json

    # Run reality-checker
    RESULT=$(cat /tmp/proof-gemini-webui/primary_work_item_reference.json | gemini -p "@reality-checker Please verify if work item $WORK_ITEM_ID is completed. Find evidence in /tmp/proof-gemini-webui/. If not, respond with NEEDS WORK and provide details of what you need to see. You may request additional proof such as screenshots or other type items be created in docs/qa-images during unit so you can examine them.  Be descriptive as to what you need to certify this ticket as unquestionably complete." 2>&1)
    RC_EXIT_CODE=$?
    
    if [ $RC_EXIT_CODE -ne 0 ]; then
      jq -c -n --arg reason "Reality checker failed to execute properly. Tell an agent to handle it, fix the problem, and try again. Result: $RESULT" '{"decision": "deny", "reason": $reason}'
      exit 0
    fi
    
    # The only guarantee is reality-checker will provide a default NEEDS WORK.
    if echo "$RESULT" | grep -q "NEEDS WORK"; then
      jq -c -n --arg reason "Reality checker blocked the transition to Done. Tell an agent to handle it. Now is a good time to read your .gemini/GEMINI.md.  Result: $RESULT" '{"decision": "deny", "reason": $reason}'
      exit 0
    else
      echo '{"decision": "allow"}'
      # Clean up proof if successful
      rm -rf /tmp/proof-gemini-webui
      exit 0
    fi
  fi
fi

# Allow anything else not explicitly blocked
echo '{"decision": "allow"}'
