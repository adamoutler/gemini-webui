---
description: Build and run gemini-webui from local source in a disposable test container, reusing the gemini-webui-dev container's port, volume, and environment.
---

# Skill: Docker Smoke Test

Use this skill whenever you need to quickly validate code changes in a full container environment — especially for testing SSH session listing, terminal launch, or any behaviour that requires the real app stack (not just unit tests).

## When to Use

- After changes to `src/process_manager.py`, `src/app.py`, or any route code
- Before recommending a commit as "working"
- When the user asks to "smoke test" or "quick-check" changes in a container

## The Script

**Location:** `scripts/smoke-test.sh` in the repo root.

### What it does

1. **Inspects `gemini-webui-dev`** to extract its host port, volume name, env vars, and network. Falls back to safe defaults (`port=5000`, no volume) if the container doesn't exist.
2. **Builds a fresh image** from the current working tree using `docker buildx build --load`.
3. **Stops `gemini-webui-dev`** (so the port is free and the volume can be reused).
4. **Runs the test container** (`gemini-webui-smoke`) on the same port with the same volume/env.
5. **On Ctrl-C:** stops the test container and restarts `gemini-webui-dev`.

## How to Invoke

```bash
# Standard smoke test (stops gemini-webui-dev, reuses its port and volume)
cd /home/adamoutler/gemini-webui
chmod +x scripts/smoke-test.sh
./scripts/smoke-test.sh

# Keep gemini-webui-dev running (test on same port will fail if port in use)
./scripts/smoke-test.sh --no-stop

# Override the host port
./scripts/smoke-test.sh --port 5002

# Use a custom image tag
./scripts/smoke-test.sh --tag gemini-webui:my-branch
```

## Key Environment Variables (override before running)

| Variable         | Default                    | Purpose                                  |
| ---------------- | -------------------------- | ---------------------------------------- |
| `DEV_CONTAINER`  | `gemini-webui-dev`         | Name of the reference container to probe |
| `TEST_CONTAINER` | `gemini-webui-smoke`       | Name of the test container to create     |
| `IMAGE_TAG`      | `gemini-webui:smoke-local` | Docker image tag to build                |
| `BYPASS_AUTH`    | `true`                     | Skip LDAP auth in test container         |
| `PLATFORM`       | `linux/amd64`              | Build platform                           |

## Verifying the Smoke Test

After the container starts, check these manually or programmatically:

1. **Health endpoint:** `curl http://localhost:<PORT>/health`
2. **Session listing:** Open the WebUI → add an SSH connection → verify sessions populate
3. **Terminal launch:** Connect to a session → verify gemini starts (not just a shell)
4. **Logs:** The script streams docker logs to stdout — check for tracebacks

## Notes

- `BYPASS_AUTH_FOR_TESTING=true` is always set so you don't need LDAP credentials
- The test container is started with `--rm` so it cleans up automatically on exit
- After Ctrl-C the script restarts `gemini-webui-dev` automatically
- The script does NOT push the image anywhere — it is purely local
