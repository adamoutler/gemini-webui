---
name: troubleshoot-zombies
description: Use this skill to rigorously test for zombie processes and ensure the Gemini WebUI application functions correctly without leaking processes on the host.
---

# QA Zombie Testing Procedure

Follow these steps exactly to reproduce and test the zombie process issue. Do not skip steps.

1. **Clean Slate:** 
   - Inspect the `gemini-webui-dev` container (`docker ps | grep gemini-webui-dev`).
   - Stop the `gemini-webui-dev` container using `docker stop gemini-webui-dev` and `docker rm gemini-webui-dev`.
   - Wait 1 minute.
   - Check the host for zombie processes: `ps -aux | awk '$8=="Z" || $8=="Z+"'`. 
   - Ensure NO zombies exist. If zombies are present, investigate their parent PIDs to see where they came from.

2. **Deploy Test Container:**
   - Recreate/Start the `gemini-webui-dev` container with local admin bypass:
     ```bash
     docker run -d --name gemini-webui-dev -p 5008:5000 -v tes_gemini-webui-dev-deploy_main_data-dev:/data -e BYPASS_AUTH_FOR_TESTING=true ghcr.io/adamoutler/gemini-webui-dev:latest
     ```

3. **Verify UI and Data:**
   - Use a headless browser script (Playwright) to visit the local page (`http://127.0.0.1:5008/`).
   - Ensure the page loads and that most connections show resumable sessions (e.g., check that `.session-item` elements exist in the DOM).

4. **Trigger the Issue:**
   - Programmatically click to resume *any* session on the page using the headless browser, OR start a new session.
   - Ensure the backend spawns the `ssh` or local processes.

5. **Observe:**
   - Wait exactly 1 minute.
   - Run `ps -aux | awk '{if ($8 == "Z" || $8 == "Z+") print $0}'` on the host to check for zombie processes.
   - Check the remote host (if applicable) for leaked `bash` or `gemini` processes.
   - If zombies exist, the test FAILS. Your fix did not work.
