import sys
sys.path.append('src')
from process_manager import build_terminal_command

# Test 1: local, start new
print(build_terminal_command(None, None, False, '/tmp', 'gemini-test'))

# Test 2: local, resume latest
print(build_terminal_command(None, None, True, '/tmp', 'gemini-test'))

# Test 3: local, resume specific
print(build_terminal_command(None, None, '1', '/tmp', 'gemini-test'))

# Test 4: local, resume boolean true passed as string from somewhere?
print(build_terminal_command(None, None, 'true', '/tmp', 'gemini-test'))
