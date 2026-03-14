#!/bin/bash
input=$(cat)
state=$(echo "$input" | jq -r '.tool_input.state')

# The Done state ID is ae56a905-81b7-4f9a-a2e5-7a842d66b8f4
if [[ "$state" == "ae56a905-81b7-4f9a-a2e5-7a842d66b8f4" ]] || [[ "$state" == "05ce5001-f07a-4126-838c-b9ebea9725ab" ]]; then
    jq -n '{
        error: "GUARDRAIL TRIGGERED: You are strictly forbidden from manually transitioning tickets to Done using update_work_item. Tickets must be closed by the QA gate via a valid `git commit`. Proceed with execution pipeline."
    }'
    exit 0
fi

echo '{"decision": "allow"}'
