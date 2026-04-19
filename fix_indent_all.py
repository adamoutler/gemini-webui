import sys

with open("src/app.py", "r") as f:
    lines = f.readlines()

out = []
in_handlers = False

for line in lines:
    if line.startswith("def register_socketio_handlers(app):"):
        in_handlers = True
        out.append(line)
        continue

    if in_handlers and line.startswith("def register_blueprints(app_instance):"):
        in_handlers = False

    if in_handlers:
        if line.startswith("    @socketio.on"):
            out.append(line)
        elif line.startswith("        def "):
            out.append("    " + line.lstrip())
        elif line.startswith("            "):
            out.append("        " + line.lstrip())
        elif line.startswith("        "):
            out.append("    " + line.lstrip())
        elif line.strip() == "":
            out.append(line)
        else:
            out.append(line)
    else:
        out.append(line)

with open("src/app.py", "w") as f:
    f.writelines(out)
