# ==========================================
# Stage 1: Builder (Dependency Installation)
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /app

# 1. Install build dependencies
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy ONLY dependency files first to leverage Docker layer caching.
# Any change to requirements.txt invalidates this and subsequent layers.
COPY requirements.txt .

# 3. Create virtual environment and install Python dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# Stage 2: Final Runtime Image
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# 1. Install runtime dependencies
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    wget \
    gpg \
    gnupg2 \
    pass \
    nodejs \
    npm \
    xclip \
    tini \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Gemini CLI via npm
RUN npm install -g @google/gemini-cli --unsafe-perm

# 3. Copy virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# LDAP & System Configuration
ENV LDAP_SERVER=
ENV LDAP_BASE_DN=
ENV LDAP_BIND_USER_DN=
ENV LDAP_BIND_PASS=
ENV LDAP_AUTHORIZED_GROUP=
ENV LDAP_FALLBACK_DOMAIN=example.com
ENV PYTHONDONTWRITEBYTECODE=1
ENV GEMINI_HOME=/home/node/.gemini

EXPOSE 5000 5002

# Create a non-root user and data directory
RUN useradd -m -u 1000 node && \
    mkdir -p /data/.gemini && \
    chown -R node:node /data && \
    ln -s /data/.gemini /home/node/.gemini && \
    chown -h node:node /home/node/.gemini && \
    mkdir -p /root && \
    ln -s /data/.gemini /root/.gemini

# 4. Copy application code LAST
# This ensures that frequent code changes don't invalidate the expensive dependency cache layers.
COPY . .

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "src/app.py"]
