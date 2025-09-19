FROM ubuntu:22.04

LABEL maintainer="bd-SrinathAkkem"
LABEL version="1.0"
LABEL description="AI-powered repository analyzer for GitHub Actions"

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    jq \
    python3.10 \
    python3-pip \
    python3-venv \
    build-essential \
    software-properties-common \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash runner

# Set working directory
WORKDIR /action

# Copy analyzer files
COPY repo_analyzer.py ./
COPY run_repo_analyzer.sh ./
COPY entrypoint.sh ./

# Make scripts executable
RUN chmod +x run_repo_analyzer.sh entrypoint.sh

# Install Python dependencies
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
    requests>=2.31.0 \
    openai>=1.0.0 \
    toml>=0.10.2 \
    PyYAML>=6.0

# Set entrypoint (keep as root since script needs to install packages)
ENTRYPOINT ["/action/entrypoint.sh"]