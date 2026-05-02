FROM mcr.microsoft.com/devcontainers/python:3.12

# System dependencies for docker-py, psycopg, pgvector
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    python3-dev \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js from NodeSource (faster than apt default)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install CLI tools
RUN npm install -g opencode-ai @anthropic-ai/claude-code @github/copilot
