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
    xclip \
    && rm -rf /var/lib/apt/lists/*

# Install Gemini CLI via npm to ensure architecture compatibility (arm64/amd64)
RUN npm install -g @google/gemini-cli

COPY . .

# Set environment variables for Gemini
ENV GEMINI_HOME=/home/node/.gemini
# Expose the Flask port
EXPOSE 5000

# Create a non-root user and data directory
RUN useradd -m -u 1000 node && \
    mkdir -p /data && \
    chown -R node:node /data

# We need access to the mounted volume for the host
CMD ["python", "src/app.py"]