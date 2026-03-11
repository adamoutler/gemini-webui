#!/bin/bash
# .gemini/hooks/prevent-curl-bypass.sh

PAYLOAD=$(cat -)
COMMAND=$(echo "$PAYLOAD" | jq -r '.tool_input.command // empty')

if [[ "$COMMAND" == *"curl "* || "$COMMAND" == *"gh "* || "$COMMAND" == *"plane "* ]]; then
  if [[ "$COMMAND" == *"status"* || "$COMMAND" == *"state"* ]] && [[ "$COMMAND" == *"Done"* || "$COMMAND" == *"ae56a905-81b7-4f9a-a2e5-7a842d66b8f4"* ]]; then
    echo '{"decision": "deny", "reason": "Bypass detected. You are strictly forbidden from closing Kanban tickets via CLI tools. Please follow the verification pipeline (create a comment with the commit hash)."}'
    exit 0
  fi
fi

echo '{"decision": "allow"}'
