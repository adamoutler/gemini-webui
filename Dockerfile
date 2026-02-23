FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dependencies needed for gemini
RUN apt-get update && apt-get install -y \
    openssh-client \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Gemini CLI via npm to ensure architecture compatibility (arm64/amd64)
RUN npm install -g @google/gemini-cli

COPY . .

# Set environment variables for Gemini
ENV GEMINI_HOME=/home/node/.gemini
# Expose the Flask port
EXPOSE 5000

# Create a non-root user
RUN useradd -m -u 1000 node

# Install SSH keys at build time
ARG USERNAME
RUN mkdir -p /home/node/.ssh && \
    chmod 700 /home/node/.ssh && \
    echo "Host *\n  StrictHostKeyChecking no\n  User $USERNAME" > /home/node/.ssh/config

COPY id_ed25519 /home/node/.ssh/id_ed25519

RUN chmod 600 /home/node/.ssh/id_ed25519 && \
    chown -R node:node /home/node/.ssh

USER node

# We need access to the mounted volume for the host
CMD ["python", "src/app.py"]