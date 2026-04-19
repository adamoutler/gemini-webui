import re

with open("src/app.py", "r") as f:
    content = f.read()

# Replace current_app with app in background_session_preloader
content = re.sub(
    r"(def background_session_preloader\(\):.*?)(def )",
    lambda m: m.group(1)
    .replace("current_app.config", "app.config")
    .replace("current_app.logger", "app.logger")
    + m.group(2),
    content,
    flags=re.DOTALL,
)

# Replace current_app with app in cleanup_orphaned_ptys
content = re.sub(
    r"(def cleanup_orphaned_ptys\(\):.*?)(def )",
    lambda m: m.group(1)
    .replace("current_app.config", "app.config")
    .replace("current_app.logger", "app.logger")
    + m.group(2),
    content,
    flags=re.DOTALL,
)

# Replace current_app with app in zombie_reaper_task
content = re.sub(
    r"(def zombie_reaper_task\(\):.*?)(def )",
    lambda m: m.group(1)
    .replace("current_app.config", "app.config")
    .replace("current_app.logger", "app.logger")
    + m.group(2),
    content,
    flags=re.DOTALL,
)

with open("src/app.py", "w") as f:
    f.write(content)
