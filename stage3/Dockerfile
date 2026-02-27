FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY stage3/src /app/src
COPY pipeline_common/src /app/pipeline_common/src
COPY stage3/pyproject.toml /app/stage3/
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
    Pillow>=10.0.0

RUN pip install --no-cache-dir -e /app/pipeline_common
RUN pip install --no-cache-dir -e /app/stage3

ENV EPOCHS=10
ENV IMAGES_PER_NODE=100
ENV INSTANCE_COUNT=1
ENV INSTANCE_TYPE=ml.m5.xlarge
ENV TRAINING_BUCKET=image-training
ENV TRAINING_PREFIX=normalized/
ENV DATASET_ID=default
ENV MLFLOW_TRACKING_URL=http://localhost:5000
ENV MLFLOW_REGISTRY_URL=http://localhost:5000
ENV MLFLOW_EXPERIMENT=image-ml-training
ENV NVME_ROOT=/mnt/nvme

ENTRYPOINT ["python", "-m", "stage3"]
