import sys

def refactor():
    with open('src/app.py', 'r') as f:
        lines = f.readlines()

    out_lines = []
    i = 0
    skip = False
    
    # We want to skip from @app.route... for specific functions until the next @app.route or @socketio.on
    funcs_to_remove = [
        "def list_hosts(",
        "def add_host(",
        "def reorder_hosts(",
        "def remove_host(",
        "def list_ssh_keys(",
        "def get_public_key(",
        "def rotate_instance_key(",
        "def add_ssh_key_text(",
        "def upload_ssh_key(",
        "def remove_ssh_key("
    ]

    while i < len(lines):
        line = lines[i]
        
        # Check if this line is an @app.route that we want to remove
        if line.startswith('@app.route'):
            # look ahead up to 5 lines to see what function it decorates
            is_target = False
            for j in range(i+1, min(i+5, len(lines))):
                if any(lines[j].startswith(f) for f in funcs_to_remove):
                    is_target = True
                    break
            
            if is_target:
                # We are skipping. Skip until the next line that starts with @app.route, @socketio, or if __name__
                i += 1
                while i < len(lines) and not (lines[i].startswith('@app.route') or lines[i].startswith('@socketio') or lines[i].startswith('if __name__') or lines[i].startswith('@app.context_processor') or lines[i].startswith('@app.before_request')):
                    i += 1
                continue # go to next iteration without incrementing i because we stopped at the next block
                
        out_lines.append(line)
        i += 1

    # Insert the blueprint registration right before if __name__ == '__main__'
    final_lines = []
    for line in out_lines:
        if line.startswith("if __name__ == '__main__':"):
            final_lines.append("from src.host_key_routes import host_key_bp\n")
            final_lines.append("app.register_blueprint(host_key_bp)\n")
            final_lines.append("\n")
        final_lines.append(line)

    with open('src/app.py', 'w') as f:
        f.writelines(final_lines)

if __name__ == '__main__':
    refactor()
