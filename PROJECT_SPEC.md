# Multi-Stage ImageML Image Pipeline Project Spec
Date: 2026-02-26

This document is intended for OpenCode, Codex, and multi-agent coding workflows to implement a practical repository to specification.

## Goals
- Provide a multi-stage pipeline for image ingestion, augmentation, normalization, training, and inference.
- Each stage is a separately buildable container image, pushed to ECR via GitHub Actions.
- Support both event-driven and scheduled polling execution.
- Stage data to local NVMe before processing.
- Use a manifest store for lineage, idempotency, and dataset tracking.
- Integrate Label Studio Pro annotations and COCO format via Label Studio SDK conversion utilities.
- Provide IaC using Terraform or OpenTofu with variants for AWS, EKS, OpenShift, and local RKE2.
- Provide devcontainers for local development and CI using Podman, RustFS, PostgreSQL, and MLflow.
- Provide a functional and performance test plan focused on data distribution, training execution, and MLflow artifacts.

## Non-Goals
- Full production orchestration for every compute substrate. Provide a clean abstraction and wiring stubs.
- Implementing a full manifest store service. Implement an adapter and document integration points.

## Pipeline Stages

### Stage 1: Ingest and Augment
Trigger:
- Event driven: S3 object created event to EventBridge to SQS to worker.
- Polling: scheduled watcher listing raw bucket prefix and consuming unprocessed objects.

Work:
- Copy input objects to local NVMe input directory.
- Convert annotations if needed:
  - Label Studio Pro export to COCO when downstream expects COCO
  - COCO to Label Studio when needed for HITL compatibility
- Apply Albumentations transforms.
- Write augmented images to S3 augmented bucket.
- Produce output manifest and publish to manifest store.

Inputs:
- S3 raw bucket and prefix
- optional annotation inputs in Label Studio or COCO format

Outputs:
- S3 augmented bucket and prefix
- stage manifest in S3 and manifest store

### Stage 2: Normalize and Resize, Multi-Variant
Trigger:
- Event driven or polling.

Work:
- Copy augmented shard to local NVMe.
- Normalize and resize images.
- Produce multiple size variants per original.
- Write normalized variants to S3 normalized bucket under variant prefixes.
- Publish manifest that includes per-variant metadata.

Configuration:
- sizes list via env var NORMALIZE_SIZES or CLI --sizes
- support tokens like 1080p and 720p and explicit WxH

### Stage 3: Training
Trigger:
- Scheduled only, default daily at 9pm US Eastern.

Work:
- Copy required shard to local NVMe.
- Launch training job.
- Log to MLflow tracking server.
- Register model in MLflow model registry.

Required configuration:
- epochs
- images per node
- instances, instance type
- training data bucket and prefix
- manifest store dataset pointer
- MLflow tracking URL
- MLflow registry URL

### Stage 4: Inference and Auto-Annotation
Trigger:
- Event driven or polling.

Work:
- Copy input images to NVMe.
- Load latest approved model from MLflow registry.
- Run inference and generate annotations compatible with Stage 1 input format.
- Write predicted annotations to HITL bucket and optional final output bucket.
- Expose Prometheus metrics endpoint and provide Grafana integration placeholders.

## Local Development and CI Environment
Provide a devcontainers setup:
- Podman and podman compose (podman-docker compatibility)
- RustFS S3-compatible storage for local testing
- PostgreSQL container for manifest store backing tests
- MLflow container for tracking and registry behavior
- local .env templates and setup script

## Infrastructure Requirements, Terraform or OpenTofu
Provide IaC variants:
- infra/tofu/aws
- infra/tofu/eks
- infra/tofu/openshift
- infra/tofu/rke2-local

Each variant should:
- provision S3 buckets or S3-compatible endpoints
- provision compute with configurable NVMe capacity
- provision ECR repos
- provision schedules and optional queues
- include bootstrapping for mounting NVMe to /mnt/nvme

## CI and Code Hygiene
- uv, ruff, pytest, lefthook, nbstripout
- enforce LF and final newline across the repository
- include scripts to check newline correctness

## Testing Requirements
See TEST_PLAN.md.

## Acceptance Criteria
- Local devcontainers environment can run Stage 1 and Stage 2 against RustFS.
- Functional tests validate:
  - staged data exists on NVMe
  - expected outputs are written to S3-compatible storage
  - manifests are written and published
- A minimal training execution can be launched and MLflow artifacts are produced.
- Performance test harness exists to measure training throughput as dataset sizes increase.
