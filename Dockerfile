# TestRunner Dockerfile
# Multi-stage build for efficient image size

FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application code
COPY src/ ./src/
COPY pyproject.toml .
COPY README.md .

# Install the package
RUN pip install --no-cache-dir -e .

# Create directories for data persistence
RUN mkdir -p /data /reports /workspace

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TESTRUNNER_DATA_DIR=/data
ENV TESTRUNNER_REPORTS_DIR=/reports

# Default working directory for target repositories
WORKDIR /workspace

# Default command
ENTRYPOINT ["testrunner"]
CMD ["--help"]
