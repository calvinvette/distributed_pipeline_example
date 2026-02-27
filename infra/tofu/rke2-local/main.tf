terraform {
  required_version = ">= 1.0"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "image-ml"
}

variable "rke2_server_ip" {
  description = "RKE2 server IP address"
  type        = string
  default     = "10.0.0.100"
}

variable "nvme_device" {
  description = "NVMe device path"
  type        = string
  default     = "/dev/nvme0n1"
}

variable "nvme_mount_point" {
  description = "NVMe mount point"
  type        = string
  default     = "/mnt/nvme"
}

locals {
  bucket_prefix = var.project_name
}

resource "local_file" "rke2_config" {
  filename = "rke2-config.yaml"
  content  = <<-EOT
server: https://${var.rke2_server_ip}:9345
token: ${var.project_name}-rke2-token
snapshot-name: default
disable:
  - rke2-coredns
  - rke2-ingress-nginx
  - rke2-kube-proxy
  - rke2-metrics-server
  EOT
}

resource "local_file" "nvme_setup_script" {
  filename = "setup-nvme.sh"
  content  = <<-EOT
#!/bin/bash
set -e

NVME_DEVICE="${var.nvme_device}"
MOUNT_POINT="${var.nvme_mount_point}"

if [ ! -b "$NVME_DEVICE" ]; then
  echo "NVMe device $NVME_DEVICE not found"
  exit 1
fi

mkfs.ext4 -F "$NVME_DEVICE"

mkdir -p "$MOUNT_POINT"

mount "$NVME_DEVICE" "$MOUNT_POINT"

echo "$NVME_DEVICE $MOUNT_POINT ext4 defaults,nofail 0 2" >> /etc/fstab

echo "NVMe mounted at $MOUNT_POINT"

mkdir -p "$MOUNT_POINT"/{input,work,output,cache}

chmod -R 755 "$MOUNT_POINT"
  EOT
}

resource "local_file" "k8s_manifest" {
  filename = "k8s-manifests.yaml"
  content  = <<-EOT
apiVersion: v1
kind: Namespace
metadata:
  name: image-ml-pipeline
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: nvme-config
  namespace: image-ml-pipeline
data:
  nvme-root: "${var.nvme_mount_point}"
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nvme-pv
spec:
  capacity:
    storage: 500Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: local-nvme
  local:
    path: ${var.nvme_mount_point}
  nodeAffinity:
    required:
      hostLabels:
        nvme: "true"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nvme-pvc
  namespace: image-ml-pipeline
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 500Gi
  storageClassName: local-nvme
  volumeMode: Filesystem
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: s3-config
  namespace: image-ml-pipeline
data:
  AWS_REGION: "us-east-1"
  S3_ENDPOINT: "http://minio:9000"
  MANIFEST_STORE_BUCKET: "manifest-store"
  MLFLOW_TRACKING_URL: "http://mlflow:5000"
  MLFLOW_REGISTRY_URL: "http://mlflow:5000"
  RAW_BUCKET: "image-raw"
  AUGMENTED_BUCKET: "image-augmented"
  NORMALIZED_BUCKET: "image-normalized"
  TRAINING_BUCKET: "image-training"
  INFERENCE_INPUT_BUCKET: "image-inference-input"
  HITL_BUCKET: "image-hitl"
  OUTPUT_BUCKET: "image-output"
  NVME_ROOT: "${var.nvme_mount_point}"
  NVME_MIN_GB: "100"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: stage1-ingest
  namespace: image-ml-pipeline
spec:
  replicas: 1
  selector:
    matchLabels:
      app: stage1-ingest
  template:
    metadata:
      labels:
        app: stage1-ingest
    spec:
      containers:
      - name: stage1
        image: image-ml-stage1:latest
        envFrom:
        - configMapRef:
            name: s3-config
        volumeMounts:
        - name: nvme
          mountPath: ${var.nvme_mount_point}
      volumes:
      - name: nvme
        persistentVolumeClaim:
          claimName: nvme-pvc
  EOT
}

resource "local_file" "docker_compose" {
  filename = "docker-compose.yaml"
  content  = <<-EOT
version: '3.8'

services:
  minio:
    image: minio/minio:latest
    container_name: ${var.project_name}-minio
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:15
    container_name: ${var.project_name}-postgres
    environment:
      POSTGRES_USER: mlops
      POSTGRES_PASSWORD: mlops
      POSTGRES_DB: mlops
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mlops"]
      interval: 5s
      timeout: 5s
      retries: 5

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    container_name: ${var.project_name}-mlflow
    depends_on:
      postgres:
        condition: service_healthy
      minio:
        condition: service_healthy
    environment:
      MLFLOW_BACKEND_STORE_URI: postgresql+psycopg://mlops:mlops@postgres:5432/mlops
      MLFLOW_ARTIFACT_ROOT: s3://mlflow-artifacts
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin
      MLFLOW_S3_ENDPOINT_URL: http://minio:9000
      AWS_DEFAULT_REGION: us-east-1
    ports:
      - "5000:5000"
    command: >
      mlflow server
      --host 0.0.0.0
      --port 5000
      --backend-store-uri "postgresql+psycopg://mlops:mlops@postgres:5432/mlops"
      --artifacts-destination "s3://mlflow-artifacts"

  minio-init:
    image: amazon/aws-cli:2.15.57
    container_name: ${var.project_name}-minio-init
    depends_on:
      minio:
        condition: service_healthy
    environment:
      AWS_ACCESS_KEY_ID: minioadmin
      AWS_SECRET_ACCESS_KEY: minioadmin
      AWS_DEFAULT_REGION: us-east-1
    entrypoint: ["/bin/sh","-c"]
    command: >
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket image-raw 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket image-augmented 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket image-normalized 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket image-training 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket image-inference-input 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket image-hitl 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket image-output 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket manifest-store 2>/dev/null || true;
      aws --endpoint-url http://minio:9000 s3api create-bucket --bucket mlflow-artifacts 2>/dev/null || true;
      echo "Buckets created"

volumes:
  minio_data:
  postgres_data:
  EOT
}

output "files_generated" {
  value = [
    local_file.rke2_config.filename,
    local_file.nvme_setup_script.filename,
    local_file.k8s_manifest.filename,
    local_file.docker_compose.filename,
  ]
}

output "nvme_setup_command" {
  value = "chmod +x ${local_file.nvme_setup_script.filename} && sudo ./${local_file.nvme_setup_script.filename}"
}

output "docker_compose_command" {
  value = "docker compose up -d"
}
