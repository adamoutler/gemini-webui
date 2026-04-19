import sys

with open("src/app.py", "r") as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if line.startswith("def get_config_paths("):
        skip = True
    elif line.startswith("def get_config("):
        skip = True
    elif line.startswith("def init_app("):
        skip = False

    if not skip:
        out.append(line)

content = "".join(out)
with open("src/app.py", "w") as f:
    f.write(content)
