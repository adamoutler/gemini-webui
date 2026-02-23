#!/bin/bash
# wait-for-receipt.sh
RECEIPT="/tmp/jenkins-receipt.log"
TIMEOUT=300

echo "Waiting for deployment receipt at $RECEIPT (max ${TIMEOUT}s)..."

# Ensure file exists
touch "$RECEIPT"

# Monitor for close_write events and check for completion marker
while true; do
    # inotifywait will block until the file is written and closed
    if ! inotifywait -q -t "$TIMEOUT" -e close_write "$RECEIPT"; then
        echo "Error: Timeout or inotifywait failed."
        exit 1
    fi

    if grep -q "Finished:" "$RECEIPT"; then
        echo "Deployment Complete. Results:"
        echo "----------------------------------------"
        cat "$RECEIPT"
        echo "----------------------------------------"
        exit 0
    fi
    # If "Finished:" isn't there yet, it might be an intermediate update
done
