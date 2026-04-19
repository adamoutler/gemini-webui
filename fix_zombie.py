with open("src/app.py", "r") as f:
    content = f.read()

content = content.replace(
    "def zombie_reaper_task():",
    "def zombie_reaper_task():\n    from src.shared_state import abandoned_pids, abandoned_pids_lock",
)

with open("src/app.py", "w") as f:
    f.write(content)
