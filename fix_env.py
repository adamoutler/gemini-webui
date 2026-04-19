import os

for root, _, files in os.walk("tests"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            if 'env["SKIP_MONKEY_PATCH"] = "false"' in content:
                new_content = content.replace(
                    'env["SKIP_MONKEY_PATCH"] = "false"',
                    'env["SKIP_MONKEY_PATCH"] = "true"',
                )
                with open(path, "w") as f:
                    f.write(new_content)
                print(f"Fixed {path}")
