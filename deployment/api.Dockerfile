FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for PyTorch/ARM64 compatibility
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV VECLIB_MAXIMUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1
ENV PYTORCH_ENABLE_MPS_FALLBACK=1

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY processing/requirements.txt /app/processing/
COPY api/requirements.txt /app/api/

# Install Python dependencies
RUN pip install --no-cache-dir -r processing/requirements.txt \
    && pip install --no-cache-dir -r api/requirements.txt

# Copy application code
COPY processing/*.py /app/processing/
COPY api/*.py /app/api/

# Create storage directory
RUN mkdir -p /app/storage

# Expose port
EXPOSE 8000

# Run the API server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
