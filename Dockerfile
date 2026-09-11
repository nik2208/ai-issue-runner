FROM python:3.12-slim

# Install system dependencies (git, curl, nodejs for npm testing, build essentials)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @earendil-works/pi-coding-agent \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy packaging configuration and install dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir hatchling && pip install --no-cache-dir .

# Copy application source code
COPY ai_runner/ ./ai_runner/
RUN pip install --no-cache-dir -e .

# Create workspace and data directory
RUN mkdir -p /workspace /root/.ai-runner
WORKDIR /workspace

EXPOSE 4242

ENTRYPOINT ["ai-runner"]
CMD ["start", "--host", "0.0.0.0", "--port", "4242"]
