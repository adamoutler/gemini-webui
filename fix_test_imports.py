import os
import glob
import re

funcs_to_move = [
    "pty_restart",
    "pty_input",
    "pty_resize",
    "session_output_reader",
    "set_winsize",
    "background_session_preloader",
    "handle_connect",
    "handle_disconnect",
    "on_join_room",
    "update_title",
    "handle_get_management_sessions",
    "handle_get_sessions",
]

for file in glob.glob("tests/unit/*.py"):
    with open(file, "r") as f:
        content = f.read()

    modified = False
    for func in funcs_to_move:
        # If func is imported from src.app, we remove it from there and add it to src.gateways.terminal_socket
        # But this is hard with multiline from src.app import ( ... )
        # Let's just find and replace occurrences of "from src.app import" that contain our funcs
        pass

    # A simpler approach: just add `from src.gateways.terminal_socket import pty_restart, session_output_reader, set_winsize, pty_input` at the top
    # And we don't care if they are still listed in `from src.app import`, because if they are removed from `src.app`, that line will crash.
    # So we must remove them from `from src.app import ...`

    lines = content.split("\n")
    new_lines = []
    in_app_import = False
    app_import_str = ""

    for i, line in enumerate(lines):
        if "from src.app import" in line:
            if "(" in line and ")" not in line:
                in_app_import = True

            # remove the func names
            for func in funcs_to_move:
                line = re.sub(r"\b" + func + r"\b,?", "", line)
            new_lines.append(line)
        elif in_app_import:
            for func in funcs_to_move:
                line = re.sub(r"\b" + func + r"\b,?", "", line)
            new_lines.append(line)
            if ")" in line:
                in_app_import = False
        else:
            new_lines.append(line)

    content = "\n".join(new_lines)
    # Add our new imports
    needed_funcs = [f for f in funcs_to_move if f in content]
    if needed_funcs:
        content = (
            f"from src.gateways.terminal_socket import {', '.join(needed_funcs)}\n"
            + content
        )

    if content != "\n".join(lines):
        with open(file, "w") as f:
            f.write(content)
            print(f"Updated {file}")
