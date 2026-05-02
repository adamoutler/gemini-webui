import re

# Precompile terminal ID regex for performance
IDENTIFICATION_REGEX = re.compile(r"\x1b\[\??\d+(?:;\d+)*c")
