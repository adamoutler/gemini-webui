with open("src/routes/terminal.py", "r") as f:
    term_content = f.read()
if "smart_file_search" not in term_content:
    term_content = term_content.replace(
        "from src.extensions import socketio",
        "from src.extensions import socketio\nfrom src.utils import smart_file_search",
    )
with open("src/routes/terminal.py", "w") as f:
    f.write(term_content)

with open("src/app.py", "r") as f:
    app_content = f.read()

# Fix UnboundLocalError by removing local assignments to app_config if any
# wait, UnboundLocalError means app_config = ... exists in the function!
import re

app_content = re.sub(
    r"(\s+)app_config = (.*?)\n", r"\1# removed local app_config\n", app_content
)

with open("src/app.py", "w") as f:
    f.write(app_content)
