import json
import os

try:
    with open("/home/adamoutler/.gemini/tmp/gemini-webui-1/tool-outputs/session-e2166e92-6bed-4128-8a43-865911fef931/mcp_kanban_list_work_items_1773261125563_0.txt", "r") as f:
        data = json.load(f)
    
    # State mapping from previous lookup
    states = {
        "31fb326d-3884-4405-8cd0-26ed5e96f4d1": "Backlog",
        "875ea790-38cf-4cbe-a2cc-9aecc7430d2a": "Todo",
        "d142bbba-7042-4eab-88bc-88dea4f60ba9": "In Progress",
        "ae56a905-81b7-4f9a-a2e5-7a842d66b8f4": "Done"
    }

    print("Open tickets related to text area/mobile/backspace:")
    for item in data:
        state_id = item.get("state")
        state_name = states.get(state_id, state_id)
        if state_name in ["Backlog", "Todo", "In Progress"]:
            name = item.get("name", "").lower()
            if "text" in name or "mobile" in name or "backspace" in name:
                print(f"[{state_name}] GEMWEBUI-{item.get('sequence_id')}: {item.get('name')}")
except Exception as e:
    print(f"Error: {e}")
