#!/bin/bash
input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name')

if [ "$tool_name" = "run_shell_command" ]; then
    command=$(echo "$input" | jq -r '.tool_input.command')
    
    # Intercept AI git commit commands unless explicitly bypassed
    if [[ "$command" =~ ^git[[:space:]]+commit ]] && [[ ! "$command" =~ SKIP_QA=1 ]] && [[ ! "$command" =~ pytest ]]; then
        
        modified_cmd="echo '--- AI QA GATE ---' && \
if [ ! -f /tmp/gemini-webui-ticket.txt ] || [ ! -s /tmp/gemini-webui-ticket.txt ]; then \
    echo 'Error: /tmp/gemini-webui-ticket.txt is missing or empty. Please create a ticket and save its ID.'; \
    exit 1; \
fi && \
TICKET_ID=\$(cat /tmp/gemini-webui-ticket.txt) && \
echo \"Running unit tests for ticket \$TICKET_ID...\" && \
source .venv/bin/activate && PYTHONPATH=. pytest tests/ > /tmp/gemini-webui-unit-test-results.txt && \
echo 'Tests passed. Asking reality-checker...' && \
cat /tmp/gemini-webui-unit-test-results.txt | gemini -y -p \"@reality-checker Please examine Kanban ticket \${TICKET_ID} via MCP and the provided unit test results from stdin. Please validate quality and completeness. Reply \\\`NEEDS WORK\\\` and an explanation if further work is required.\" > /tmp/gemini-webui-reality-results.txt && \
if grep -q 'NEEDS WORK' /tmp/gemini-webui-reality-results.txt; then \
    echo '--- QA REJECTED ---'; \
    cat /tmp/gemini-webui-reality-results.txt; \
    exit 1; \
else \
    echo '--- QA APPROVED ---'; \
    $command && ./scripts/increment_version.sh; \
fi"
        
        jq -n --arg cmd "$modified_cmd" '{decision: "modify", modified_args: {command: $cmd}}'
        exit 0
    fi
fi

echo '{"decision": "allow"}'
