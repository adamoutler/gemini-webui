---
name: push-protocol
description: Important information for pushing changes to the Gemini WebUI repository. Redirects manual git push operations to the custom git p alias.
---

# Gemini WebUI Push Protocol

> [!IMPORTANT]
> **MANDATORY: ALWAYS USE `git p` FOR DEPLOYMENT.**
> Never use `git push` directly in this repository.

To ensure successful deployments and environment consistency, follow these rules:

## 🚀 Use `git p` instead of `git push`

The custom alias `git p` is mandatory for all pushes. It performs two critical functions:
1.  **Synchronous Push**: Pushes your current branch to `origin`.
2.  **Deployment Monitoring**: Automatically executes `./jenkins/wait-for-receipt.sh` to block until the Jenkins deployment is complete and verified.

## ✅ Verification

Do not consider your task finished until `git p` completes and the deployment receipt shows `SUCCESS`. If a build fails, check the logs for the specific error.
