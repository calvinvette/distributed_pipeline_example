FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY stage1/src /app/src
COPY pipeline_common/src /app/pipeline_common/src
COPY stage1/pyproject.toml /app/stage1/
COPY pipeline_common/pyproject.toml /app/pipeline_common/

ENV PYTHONPATH=/app/pipeline_common/src:/app/src:${PYTHONPATH}

RUN pip install --no-cache-dir \
    boto3>=1.34.0 \
    botocore>=1.34.0 \
    python-dotenv>=1.0.0 \
    pydantic>=2.5.0 \
    albumentations>=1.3.0 \
    opencv-python-headless>=4.8.0 \
    Pillow>=10.0.0 \
    label-studio-sdk>=1.0.0

RUN pip install --no-cache-dir -e /app/pipeline_common
RUN pip install --no-cache-dir -e /app/stage1

ENV MODE=poll
ENV RAW_BUCKET=image-raw
ENV AUGMENTED_BUCKET=image-augmented
ENV OUTPUT_PREFIX=augmented/
ENV DATASET_ID=default
ENV NVME_ROOT=/mnt/nvme
ENV MANIFEST_STORE_BUCKET=manifest-store

ENTRYPOINT ["python", "-m", "stage1"]
