# Environment Context

This environment is shared with an AI working in a container named **Meatloaf**.

# How to run commands on the host

To run commands on the host machine from this container, you should use SSH. 

Example:
```bash
ssh ${USERNAME}@192.168.1.101 'your command here'
```
The container is pre-configured with the necessary SSH keys for the **${USERNAME}** user.

# Project Standards & Tooling

## Kanban Issue Management
**MANDATORY**: When creating or updating work items in Kanban, always use Markdown for the `description_html` field. The system processes Markdown correctly, but raw HTML may be rendered literally, making the tickets unreadable. Ensure all task lists, headers, and code blocks use standard GitHub-flavored Markdown. 