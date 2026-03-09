#!/usr/bin/env python3
import os
import json
import urllib.request
import sys

WORKSPACE_SLUG = "gemwebui"
PROJECT_ID = "06865fee-010e-4f05-84e5-5014b254f5f6"
DONE_STATE_ID = "ae56a905-81b7-4f9a-a2e5-7a842d66b8f4"
API_BASE = f"https://kanban.hackedyour.info/api/v1/workspaces/{WORKSPACE_SLUG}/projects/{PROJECT_ID}"

def get_api_key():
    key = os.environ.get("KANBAN_API_KEY")
    if key:
        return key
    print("Error: KANBAN_API_KEY not found in environment.")
    print("Please export KANBAN_API_KEY or use the value defined in .gemini/settings.json.")
    sys.exit(1)

def fetch(url, key):
    req = urllib.request.Request(url, headers={
        "X-Api-Key": key,
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"API request failed: {e}")
        sys.exit(1)

def audit():
    key = get_api_key()

    print(f"Fetching all DONE issues from Plane Kanban...")
    issues = []
    
    # Handle pagination if necessary (Plane uses cursor-based pagination, we'll fetch until empty)
    cursor = ""
    while True:
        url = f"{API_BASE}/issues/?state={DONE_STATE_ID}&per_page=100"
        if cursor:
            url += f"&cursor={cursor}"
        
        data = fetch(url, key)
        results = data.get("results", [])
        issues.extend(results)
        
        cursor = data.get("next_cursor")
        if not data.get("next_page_results") or not cursor:
            break

    print(f"Found {len(issues)} done issues total. Auditing those with sequence_id >= 137...")

    violating_issues = []

    for issue in issues:
        seq_id = issue.get("sequence_id", 0)
        state_id = issue.get("state")
        
        if seq_id >= 137 and state_id == DONE_STATE_ID:
            issue_id = issue["id"]
            name = issue["name"]
            
            # Fetch comments
            comments_url = f"{API_BASE}/issues/{issue_id}/comments/"
            comments_data = fetch(comments_url, key)
            comments = comments_data.get("results", [])
            
            has_commit_url = False
            for comment in comments:
                # Plane comments have HTML content
                content = comment.get("comment_html", "") or ""
                # Also check stripped text just in case
                stripped = comment.get("comment_stripped", "") or ""
                if "https://git.adamoutler.com/aoutler/gemini-webui/commit/" in content or \
                   "https://git.adamoutler.com/aoutler/gemini-webui/commit/" in stripped:
                    has_commit_url = True
                    break
            
            if not has_commit_url:
                violating_issues.append((seq_id, name, issue_id))
    
    if violating_issues:
        print("\n--- AUDIT FAILED ---")
        print("The following tickets are marked as DONE but are missing the required Git commit URL in their comments:")
        for seq_id, name, issue_id in sorted(violating_issues, key=lambda x: x[0]):
            print(f"GEMWE-{seq_id}: {name} (ID: {issue_id})")
        print("\nRECOMMENDATION: These tickets should be moved back to 'In Progress' or have the commit URL added.")
        sys.exit(1)
    else:
        print("\n--- AUDIT PASSED ---")
        print("All DONE tickets with sequence ID >= 137 have a valid commit URL.")
        sys.exit(0)

if __name__ == "__main__":
    audit()