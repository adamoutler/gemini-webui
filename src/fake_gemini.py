#!/usr/bin/env python3
import sys
import os
import time
import argparse
import select
import termios
import tty

def get_char():
    """Reads a single character from stdin."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def run_fake_gemini():
    parser = argparse.ArgumentParser(description="High-Fidelity Fake Gemini CLI Simulator")
    parser.add_argument("--scenario", type=str, default="default", help="Scenario to run")
    args = parser.parse_args()

    # Initial Welcome
    sys.stdout.write("\x1b[2J\x1b[H") # Clear screen and home
    sys.stdout.write("\x1b[1;36m[Fake Gemini v2.0 - High Fidelity Mode]\x1b[0m\r\n")
    sys.stdout.write(f"\x1b[1;34mScenario: {args.scenario}\x1b[0m\r\n")
    
    if "GEMINI_WEBUI_HARNESS_ID" not in os.environ:
        sys.stdout.write("\x1b[31m[WARNING: HARNESS BYPASSED]\x1b[0m\r\n")
    
    sys.stdout.write("\x1b[32mReady for input. Type 'EXIT' to quit.\x1b[0m\r\n")
    sys.stdout.write("> ")
    sys.stdout.flush()

    input_buffer = ""
    memory = {}

    while True:
        # Check if stdin has data
        if select.select([sys.stdin], [], [], 0.1)[0]:
            char = get_char()
            
            # Handle Backspace
            if char in ("\x7f", "\x08"):
                if len(input_buffer) > 0:
                    input_buffer = input_buffer[:-1]
                    sys.stdout.write("\b \b") # Backspace, Space, Backspace
                    sys.stdout.flush()
                continue
            
            # Handle Enter
            if char in ("\r", "\n"):
                sys.stdout.write("\r\n")
                line = input_buffer.strip()
                
                if line == "EXIT":
                    sys.stdout.write("\x1b[1;33mGoodbye!\x1b[0m\r\n")
                    sys.stdout.flush()
                    break
                
                elif "TRUECOLOR" in line:
                    sys.stdout.write("\x1b[38;2;255;0;0mR\x1b[38;2;0;255;0mG\x1b[38;2;0;0;255;1mB\x1b[0m - TrueColor Test\r\n")
                    for i in range(0, 256, 16):
                        sys.stdout.write(f"\x1b[48;2;{i};0;{255-i}m ")
                    sys.stdout.write("\x1b[0m\r\n")
                
                elif "COMPLEX" in line:
                    sys.stdout.write("\x1b[1;31mBold \x1b[2mDim \x1b[3mItalic \x1b[4mUnderline \x1b[5mBlink \x1b[7mReverse \x1b[8mHidden\x1b[0m\r\n")
                    sys.stdout.write("\x1b[38;5;214m256-Color Orange\x1b[0m - \x1b[48;5;124mDark Red Background\x1b[0m\r\n")
                
                elif "BURST" in line:
                    for i in range(50):
                        sys.stdout.write(f"\x1b[1;3{i%7+1}mLine {i}: Bursting with high-fidelity output for xterm.js verification.\x1b[0m\r\n")
                        sys.stdout.flush()
                        time.sleep(0.01)
                
                elif line:
                    sys.stdout.write(f"You typed: {repr(line)}\r\n")
                
                sys.stdout.write("> ")
                sys.stdout.flush()
                input_buffer = ""
                continue
            
            # Handle Ctrl+C
            if char == "\x03":
                sys.stdout.write("^C\r\n")
                sys.stdout.write("> ")
                sys.stdout.flush()
                input_buffer = ""
                continue

            # Echo character and add to buffer
            sys.stdout.write(char)
            sys.stdout.flush()
            input_buffer += char

if __name__ == "__main__":
    run_fake_gemini()
