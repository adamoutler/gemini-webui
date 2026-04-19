import os

for root, _, files in os.walk("tests"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            if 'env["FLASK_USE_RELOADER"] = "false"' in content:
                if 'env["SKIP_MONKEY_PATCH"] = "false"' not in content:
                    new_content = content.replace(
                        'env["FLASK_USE_RELOADER"] = "false"',
                        'env["FLASK_USE_RELOADER"] = "false"\n    env["SKIP_MONKEY_PATCH"] = "false"',
                    )
                    with open(path, "w") as f:
                        f.write(new_content)
                    print(f"Fixed {path}")
