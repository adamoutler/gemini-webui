import re

with open('src/app.py', 'r') as f:
    content = f.read()

def remove_route(content, func_name):
    pattern = r"@app\.route\('[^']+',\s*methods=\[[^\]]+\]\)\n@authenticated_only\ndef " + func_name + r"\(.*?\):\n(?:(?: {4}.*\n)*|(?:\n)*)*"
    return re.sub(pattern, '', content)

def remove_route_no_args(content, func_name):
    # Matches functions until the next @app.route
    # We can use a simpler approach: regex from @app.route to the next @app.route or @socketio or if __name__
    pass

routes_to_remove = [
    "list_hosts",
    "add_host",
    "reorder_hosts",
    "remove_host",
    "list_ssh_keys",
    "get_public_key",
    "rotate_instance_key",
    "add_ssh_key_text",
    "upload_ssh_key",
    "remove_ssh_key"
]

import ast

class RouteRemover(ast.NodeTransformer):
    pass

# Simpler way with AST is complex to preserve comments/formatting. 
# Let's just find lines and delete them.
lines = content.split('\n')
out_lines = []
skip = False
for line in lines:
    if line.startswith('@app.route'):
        if any(f"def {name}(" in content[content.find(line):content.find(line)+300] for name in routes_to_remove if skip == False): # Just a rough heuristic
            pass

