#!/usr/bin/env bash

# Read JSON input from Gemini CLI
input=$(cat)

# Extract tool name
tool_name=$(echo "$input" | jq -r '.tool_name')

if [ "$tool_name" = "run_shell_command" ]; then
    command=$(echo "$input" | jq -r '.tool_input.command')
    
    # Check if command is exactly "git push" or starts with "git push "
    if [[ "$command" =~ ^git\ push ]] && [[ ! "$command" =~ wait-for-receipt ]]; then
        # Append the wait script
        modified_cmd="$command && ./jenkins/wait-for-receipt.sh"
        jq -n --arg cmd "$modified_cmd" '{decision: "modify", modified_args: {command: $cmd}}'
        exit 0
    fi
fi

# Default to allow
echo '{"decision": "allow"}'
