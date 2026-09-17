# IBVAP backend — FastAPI AI microservice
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Runtime deps only (training/optional deps live in requirements-training.txt)
COPY requirements.txt requirements-cuda.txt ./
RUN pip install -r requirements.txt

# GPU build: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build`.
# The CUDA PyTorch/onnxruntime wheels bundle their own CUDA libraries, so the slim
# base works as long as the host exposes the GPU (NVIDIA Container Toolkit).
ARG INSTALL_CUDA=0
RUN if [ "$INSTALL_CUDA" = "1" ]; then pip install -r requirements-cuda.txt; fi

COPY . .

# Writable dirs owned by the runtime user; application code stays root-owned
RUN mkdir -p outputs/snapshots outputs/logs outputs/metrics outputs/videos data \
    && useradd -m -r -s /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app/outputs /app/data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=40s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health').status==200 else 1)"

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
