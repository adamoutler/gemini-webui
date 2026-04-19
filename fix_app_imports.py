import re

with open("src/app.py", "r") as f:
    content = f.read()

# Add missing imports
if "from src.shared_state import" not in content:
    content = content.replace(
        "import pty",
        "from src.shared_state import abandoned_pids, abandoned_pids_lock, session_results_cache, session_results_cache_lock\nimport pty",
    )

# Remove session_results_cache declarations
content = re.sub(r"session_results_cache = \{.*?\n", "", content)
content = re.sub(r"session_results_cache_lock = threading\.Lock\(\)\n", "", content)

# Remove abandoned_pids declarations
content = re.sub(r"abandoned_pids = set\(\)\n", "", content)
content = re.sub(r"abandoned_pids_lock = threading\.Lock\(\)\n", "", content)

# Remove kill_and_reap
content = re.sub(r"def kill_and_reap.*?pass\n\n\n", "\n\n", content, flags=re.DOTALL)

with open("src/app.py", "w") as f:
    f.write(content)
