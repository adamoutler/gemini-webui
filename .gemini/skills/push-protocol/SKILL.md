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

> [!CAUTION]
> **CONTEXT LOSS WARNING**: Because this repository uses zero-downtime deployments that restart the server, your current conversation context with the Gemini CLI may be lost during the reset. 
> 
> **MANDATORY**: Before executing `git p`, you MUST explicitly state: 
> "I acknowledge I may lose context of this transaction when the system resets."


## ✅ Verification

Do not consider your task finished until `git p` completes and the deployment receipt shows `SUCCESS`. If a build fails, check the logs for the specific error.
