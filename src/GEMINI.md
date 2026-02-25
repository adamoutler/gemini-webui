# Environment Context

This environment is shared with an AI working in a container named **Meatloaf**.

# How to run commands on the host

To run commands on the host machine from this container, you should use SSH. 

Example:
```bash
ssh ${USERNAME}@192.168.1.101 'your command here'
```
The container is pre-configured with the necessary SSH keys for the **${USERNAME}** user. 