import re

with open("src/app.py", "r") as f:
    content = f.read()

# Fix @app.before_request concatenation
content = content.replace(")@app.before_request", ")\n\n\n@app.before_request")

with open("src/app.py", "w") as f:
    f.write(content)

with open("src/routes/terminal.py", "r") as f:
    term_content = f.read()

# Add missing smart_file_search
if "smart_file_search" not in term_content:
    term_content = term_content.replace(
        "from src.extensions import socketio",
        "from src.extensions import socketio\nfrom src.utils import smart_file_search",
    )

with open("src/routes/terminal.py", "w") as f:
    f.write(term_content)

# Fix tests using src.app.get_config
import os

for root, dirs, files in os.walk("tests/unit"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r") as f:
                test_content = f.read()
            if "src.app.get_config" in test_content:
                test_content = test_content.replace(
                    "src.app.get_config_paths", "src.config.get_config_paths"
                )
                test_content = test_content.replace(
                    "src.app.get_config", "src.config.get_config"
                )
                with open(path, "w") as f:
                    f.write(test_content)

# Fix UnboundLocalError for app_config in pty_restart
# It was likely not imported or shadowed. Let's check app.py for `app_config =`
