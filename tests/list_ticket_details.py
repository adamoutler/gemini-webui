import json
import os

target_tickets = [210, 209, 197, 183]

try:
    with open("/home/adamoutler/.gemini/tmp/gemini-webui-1/tool-outputs/session-e2166e92-6bed-4128-8a43-865911fef931/mcp_kanban_list_work_items_1773261125563_0.txt", "r") as f:
        data = json.load(f)
    
    print("=== Text Area Kanban Tickets ===")
    for item in data:
        seq = item.get("sequence_id")
        if seq in target_tickets:
            print(f"--- GEMWEBUI-{seq}: {item.get('name')} ---")
            print(item.get("description_html", "No description"))
            print("\n")
except Exception as e:
    print(f"Error: {e}")
