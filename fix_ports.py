import os
import re


def fix_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # Regex to find 'import random' followed by 'port = str(random.randint(...))'
    # and replace with socket logic
    pattern = r"    import random\s+port = str\(random\.randint\(\d+,\s*\d+\)\)"
    replacement = """    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = str(s.getsockname()[1])"""

    new_content = re.sub(pattern, replacement, content)

    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"Fixed {filepath}")


for root, _, files in os.walk("tests"):
    for file in files:
        if file.endswith(".py"):
            fix_file(os.path.join(root, file))
