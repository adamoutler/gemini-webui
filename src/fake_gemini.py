try:
    from config import env_config
except ImportError:
    from src.config import env_config
#!/usr/bin/env python3
import sys
import os
import time

def run_fake_gemini():
    if "GEMINI_WEBUI_HARNESS_ID" not in os.environ:
        time.sleep(5)
        print('\x1b[31m[UNDEFINITIVE PROOF - BYPASSED HARNESS]\x1b[0m\r\n')
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
        elif "BURST" in line:
            for i in range(200):
                print(f"Line {i}: This is a long line of text that might even wrap if it gets long enough to wrap around the terminal width. Let's make it sufficiently long.")
            sys.stdout.flush()
        elif "TRUECOLOR" in line:
            print("\033[38;2;255;87;51mThis is custom red text\033[0m")
            print("\033[48;2;51;255;87mThis has a custom green background\033[0m")
            print("\033[38;2;87;51;255m\033[48;2;255;255;0mCustom purple text on custom yellow background\033[0m")
            sys.stdout.flush()
        else:
            print(f"You said: {line}")
            sys.stdout.flush()

if __name__ == "__main__":
    run_fake_gemini()
# dummy comment
# re-trigger qa gate
