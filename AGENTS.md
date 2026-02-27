# AGENTS

This file defines recommended agent roles and a suggested OpenCode multi-agent orchestration plan.

## Orchestration Style
Use parallel agents with narrow ownership:
- shared libraries and architecture first
- then per-stage implementation
- then infra variants
- then devcontainers and test harness
- then integration pass

Keep each agent's output in clearly named commits or patches. Prefer short cycles:
- plan, implement, test, document
- merge, then iterate

## Agent Roles

### Agent: Repo Architect
Responsibilities:
- Create repository skeleton and shared libraries
- Define config contracts, env templates, and interfaces for:
  - S3 endpoints
  - NVMe staging
  - manifest store adapter
  - MLflow endpoints
- Ensure code hygiene and developer ergonomics:
  - uv
  - lefthook
  - nbstripout
  - LF and final newline enforcement

Deliverables:
- Makefile, pyproject.toml, lefthook.yml, scripts
- pipeline_common modules including:
  - s3 IO abstraction with endpoint configuration
  - nvme staging helpers
  - manifest store adapter interface

### Agent: Stage 1 Engineer
Responsibilities:
- Implement Stage 1 ingest and augmentation
- Support both event-driven and polling modes
- Implement NVMe staging and publish manifests
- Integrate Label Studio and COCO handling using Label Studio SDK converters

### Agent: Stage 2 Engineer
Responsibilities:
- Implement Stage 2 normalization with multi-variant resizing
- Support configurable sizes and variant naming
- NVMe staging required
- Optional GPU acceleration path stub

### Agent: Stage 3 Engineer
Responsibilities:
- Implement training launcher and configuration
- Support epochs and images per node
- Support configurable training bucket and prefix
- Log parameters, metrics, and artifacts to MLflow
- Register model in MLflow registry or provide a clean stub interface

### Agent: Stage 4 Engineer
Responsibilities:
- Implement inference and auto-annotation
- Load latest approved model from MLflow registry
- Write HITL-compatible annotations
- Expose Prometheus metrics and provide examples for Grafana integration
- NVMe staging required

### Agent: Dev Environment Engineer
Responsibilities:
- Implement devcontainers environment:
  - Podman based
  - RustFS S3-compatible endpoint
  - PostgreSQL container
  - MLflow container
- Provide scripts to run functional tests locally
- Provide documentation for local end-to-end execution

### Agent: Infrastructure Engineer
Responsibilities:
- Create Terraform or OpenTofu variants:
  - AWS
  - EKS
  - OpenShift
  - local RKE2
- Ensure NVMe configuration is explicit and configurable
- Provide bootstrap to mount NVMe under /mnt/nvme
- Provide outputs to integrate with compute substrate wiring

### Agent: Test Engineer
Responsibilities:
- Implement TEST_PLAN.md as runnable test scripts:
  - functional tests for RustFS pipeline
  - NVMe staging verification
  - Label Studio and COCO conversion tests
  - minimal training run validation and MLflow artifact checks
  - performance tests for training throughput

## Suggested Execution Order
1. Repo Architect: skeleton, shared libs, config, hygiene
2. Dev Environment Engineer: devcontainers, RustFS, Postgres, MLflow working
3. Stage 1 and Stage 2 Engineers: implement stages, unit tests, functional tests
4. Test Engineer: functional harness and performance harness
5. Infrastructure Engineer: tofu variants and NVMe provisioning
6. Stage 3 and Stage 4 Engineers: training launcher, inference, metrics
7. Repo Architect: integration pass, docs pass, acceptance verification

## Definition of Done Checklist
- Local devcontainers runs Stage 1 and Stage 2 against RustFS
- Multi-variant normalization works and manifests capture variants
- NVMe staging is used and validated by tests
- MLflow shows artifacts for minimal training run
- Terraform or OpenTofu validate passes for each variant
- CI workflows are syntactically valid and per-stage builds exist
