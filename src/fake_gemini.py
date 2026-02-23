#!/usr/bin/env python3
import sys
import time

print("Welcome to Fake Gemini")
sys.stdout.flush()

memory = {}

while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    
    if "Remember this TEST_VALUE:" in line:
        val = line.split(":")[-1].strip()
        memory['TEST_VALUE'] = val
        print(f"I will remember TEST_VALUE: {val}")
        sys.stdout.flush()
    elif "What is the TEST_VALUE" in line or "What was the TEST_VALUE" in line or "Do you still remember the TEST_VALUE" in line:
        if 'TEST_VALUE' in memory:
            print(f"The TEST_VALUE is {memory['TEST_VALUE']}")
        else:
            print("I don't know the TEST_VALUE.")
        sys.stdout.flush()
    else:
        print(f"You said: {line}")
        sys.stdout.flush()
