# Browser Sharing Skill

This skill provides the command to share a local Google Chrome instance with Gemini via remote debugging.

## Sharing Command

To start a Chrome instance that can be shared with Gemini, run:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

## How to use
1. Run the command on your host machine.
2. Tell Gemini that the browser is ready on port 9222.
3. Gemini can then use the `chrome-devtools` skill to connect to this instance.
