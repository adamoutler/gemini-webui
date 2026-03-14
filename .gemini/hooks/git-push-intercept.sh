#!/bin/bash
input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name')

if [[ "$tool_name" =~ run_shell_command|Bash|shell ]]; then
    command=$(echo "$input" | jq -r '.tool_input.command')

    # Block 'git push'
    if [[ "$command" =~ ^git[[:space:]]+push ]]; then
        jq -n -c '{decision: "deny", reason: "git push is blocked. git p is the only way."}'
        exit 0
    fi
fi

# Default to allow
echo '{"decision": "allow"}'
