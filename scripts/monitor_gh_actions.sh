#!/bin/bash
# Monitor the latest GitHub Action run for the repository

REPO="adamoutler/gemini-webui"
echo "Fetching latest run for $REPO..."

# Get the latest run ID
RUN_ID=$(gh run list --repo "$REPO" --limit 1 --json databaseId --jq '.[0].databaseId')

if [ -z "$RUN_ID" ] || [ "$RUN_ID" == "null" ]; then
    echo "No GitHub Actions runs found or could not fetch run ID."
    exit 1
fi

echo "Watching GitHub Action Run ID: $RUN_ID"
gh run watch "$RUN_ID" --repo "$REPO"
