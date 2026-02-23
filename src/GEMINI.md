# Environment Context

This environment is shared with an AI working in a container named **Meatloaf**.

# How to run commands on the host

To run commands on the host machine from this container, you should use SSH. 

Example:
```bash
ssh ${USERNAME}@192.168.1.101 'your command here'
```
The container is pre-configured with the necessary SSH keys for the **${USERNAME}** user. 

You can also interact with the host via the mounted `~/Gemini` directory, which is mapped to `/root/Gemini` inside the container. Scripts or data placed here can be executed or read by host cron jobs or other monitoring agents.