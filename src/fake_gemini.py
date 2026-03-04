#!/usr/bin/env python3
import sys

def run_fake_gemini():
    print("Welcome to Fake Gemini")
    sys.stdout.flush()

    memory = {}

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        print(f"RAW_LINE_RECEIVED: {repr(line)}")
        sys.stdout.flush()
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
        elif "\x1b" in line:
            print(f"ALT_ENTER_RECEIVED: {repr(line)}")
            sys.stdout.flush()
        elif "EXIT" in line:
            break
        else:
            print(f"You said: {line}")
            sys.stdout.flush()

if __name__ == "__main__":
    run_fake_gemini()
