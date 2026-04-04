FROM python:3.11-slim

# LDAP Configuration
ENV LDAP_SERVER=
ENV LDAP_BASE_DN=
ENV LDAP_BIND_USER_DN=
ENV LDAP_BIND_PASS=
ENV LDAP_AUTHORIZED_GROUP=
ENV LDAP_FALLBACK_DOMAIN=example.com

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dependencies needed for gemini
RUN apt-get update && apt-get install -y \
    openssh-client \
    curl \
    wget \
    build-essential \
    python3-dev \
    libffi-dev \
    gpg \
    gnupg2 \
    pass \
    nodejs \
    npm \
    xclip \
    tini \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Set environment variables for Gemini
ENV PYTHONDONTWRITEBYTECODE=1
ENV GEMINI_HOME=/home/node/.gemini
# Expose the Flask port
EXPOSE 5000

# Create a non-root user and data directory
RUN useradd -m -u 1000 node && \
    mkdir -p /data/.gemini && \
    chown -R node:node /data && \
    ln -s /data/.gemini /home/node/.gemini && \
    chown -h node:node /home/node/.gemini && \
    mkdir -p /root && \
    ln -s /data/.gemini /root/.gemini

# Install Gemini CLI via npm at the end to ensure it's not shadowed
RUN npm install -g @google/gemini-cli --unsafe-perm

# We need access to the mounted volume for the host
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "src/app.py"]
