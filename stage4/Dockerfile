FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY stage4/src /app/src
COPY pipeline_common/src /app/pipeline_common/src
COPY stage4/pyproject.toml /app/stage4/
COPY pipeline_common/pyproject.toml /app/pipeline_common/

ENV PYTHONPATH=/app/pipeline_common/src:/app/src:${PYTHONPATH}
ENV PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir \
    boto3>=1.34.0 \
    botocore>=1.34.0 \
    python-dotenv>=1.0.0 \
    pydantic>=2.5.0 \
    mlflow>=2.8.0 \
    torch>=2.0.0 \
    torchvision>=0.15.0 \
    opencv-python-headless>=4.8.0 \
    Pillow>=10.0.0 \
    flask>=3.0.0 \
    prometheus-client>=0.19.0

RUN pip install --no-cache-dir -e /app/pipeline_common
RUN pip install --no-cache-dir -e /app/stage4

ENV MODE=poll
ENV INFERENCE_INPUT_BUCKET=image-inference-input
ENV HITL_BUCKET=image-hitl
ENV OUTPUT_BUCKET=image-output
ENV INPUT_PREFIX=inference/
ENV OUTPUT_PREFIX=predictions/
ENV DATASET_ID=default
ENV MODEL_NAME=image-ml-model
ENV MODEL_STAGE=Production
ENV MLFLOW_TRACKING_URL=http://localhost:5000
ENV MLFLOW_REGISTRY_URL=http://localhost:5000
ENV NVME_ROOT=/mnt/nvme
ENV METRICS_PORT=8000
ENV POLL_INTERVAL=60

EXPOSE 8000

ENTRYPOINT ["python", "-m", "stage4"]
