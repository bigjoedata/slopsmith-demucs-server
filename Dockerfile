# Use official PyTorch runtime with CUDA 12.1 pre-installed
FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up work directory
WORKDIR /app

# Upgrade pip itself
ARG PIP_VERSION=26.1.1
RUN pip install --no-cache-dir "pip==${PIP_VERSION}"

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set up environment variables for persistent caching under /config
ENV SLOPSMITH_DEMUCS_CACHE=/config/cache/jobs
ENV TORCH_HOME=/config/cache/torch
ENV HF_HOME=/config/cache/huggingface

# Create the /config and cache directories.
# NOTE: The container deliberately runs as root (matching the main slopsmith container's architecture).
# This is required for Unraid/NAS volume mount compatibility, preventing PermissionError
# when writing to host-mounted appdata directories owned by nobody:users or root.
RUN mkdir -p /config/cache/jobs /config/cache/torch /config/cache/huggingface

# Expose target API port
EXPOSE 8000

# Run the FastAPI server (PORT env is supported, defaulting to 8000)
ENV PORT=8000
CMD ["python", "server.py", "--host", "0.0.0.0"]
