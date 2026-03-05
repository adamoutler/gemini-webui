import os
import json
with open('src/app.py') as f:
    pass # Cannot easily extract runtime DATA_DIR from here without executing

import importlib.util
import sys

# Load config
try:
    with open('/data/config.json') as f:
        print(json.load(f))
except Exception as e:
    print(e)
