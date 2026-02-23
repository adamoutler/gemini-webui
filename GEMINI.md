# Environment Context

This environment is shared with an AI working in a container named **Meatloaf**.

# How to run commands on the host

To run commands on the host machine from this container, you should use SSH. 

Example:
```bash
ssh user@host_ip 'your command here'
```
Ensure that the container has the necessary SSH keys mounted or configured if passwordless auth is desired. 

You can also interact with the host via the mounted `~/Gemini` directory, which is mapped to `/root/Gemini` inside the container. Scripts or data placed here can be executed or read by host cron jobs or other monitoring agents.