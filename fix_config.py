import os

with open("src/config.py", "r") as f:
    content = f.read()

content = content.replace(
    "def load_config(data_dir=None):", "def get_config(data_dir=None):"
)
content = content.replace(
    "self._config = load_config(self._data_dir)",
    "self._config = get_config(self._data_dir)",
)

with open("src/config.py", "w") as f:
    f.write(content)
