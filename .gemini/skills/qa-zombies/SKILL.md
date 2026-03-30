---
name: troubleshoot-zombies
description: Use this skill to rigorously test for zombie processes and ensure the Gemini WebUI application functions correctly without leaking processes on the host.
---

# QA Zombie Testing Procedure

Follow these steps exactly to reproduce and test the zombie process issue. Do not skip steps.

**CRITICAL WARNING regarding Volumes:** 
You MUST NOT modify or delete the user's volume `tes_gemini-webui-dev-deploy_main_data-dev`. Treat it as read-only or mount it as requested, but NEVER delete or intentionally alter its contents as part of your cleanup or testing phases.

**Troubleshooting Lead:** 
The user noted that there are precisely 2 SSH connections configured to use password auth (no SSH keys provided) which fail to connect, and there happen to be exactly 2 zombie processes. Keep this in mind—failed SSH connections might be the root cause of the zombies.

1. **Clean Slate:** 
   - Remove any existing test containers: `docker rm -f gemini-zombie-test`
   - Clear out other potential offenders if necessary (e.g., `docker rm -f gemini-webui-production gemini-webui-dev gemini-webui-gemini-web-1`)
   - Check the host for zombie processes: `top -b -n 1 | grep zombie`
   - Ensure 0 zombies exist before proceeding.

2. **Build and Deploy Test Container:**
   - Build the local image: `docker build -t gemini .`
   - Start the test container (remembering the volume warning):
     ```bash
     docker run --name gemini-zombie-test -v tes_gemini-webui-dev-deploy_main_data-dev:/data -p 5500:5000 -d gemini
     ```

3. **Observe:**
   - Wait 5 seconds: `sleep 5`
   - Check for zombie processes again: `top -b -n 1 | grep zombie`
   - If any zombie processes are present, the test FAILS. The application leaked processes on startup.
