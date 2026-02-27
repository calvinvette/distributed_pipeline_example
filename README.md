# ImageML Multi-Stage Image Pipeline

## What This Is
This project defines a modular, multi-stage image pipeline for ImageML workloads. 

Key properties:
- Pipeline boundaries are S3-compatible buckets and manifests.
- Each pipeline stage is a separate container image, built and pushed to ECR via GitHub Actions.
- Stages support event-driven execution and scheduled polling.
- Data is staged to local NVMe on the compute node for performance.
- Training and inference integrate with MLflow for tracking and registry.
- Annotations originate from Label Studio Pro and can be in Label Studio format or COCO.
- A manifest store provides dataset lineage, idempotency, and stage completion markers.

## High-Level Overview for New Team Members and Technical Management
The pipeline is split into stages so the expensive work is done once and reused:
- Stage 1 ingests and augments images, then writes artifacts plus a manifest.
- Stage 2 normalizes and produces multiple size variants, then writes artifacts plus a manifest.
- Stage 3 trains on the normalized dataset without repeating preprocessing and logs everything to MLflow.
- Stage 4 runs inference, generates annotations, and feeds HITL review and retraining loops.

Why this matters:
- Faster retraining because you do not redo validation or normalization for every training run.
- Easier scaling because stages are independent and mostly embarrassingly parallel.
- Better reproducibility because manifests and staged data capture dataset lineage.

## Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:
- **VSCode** with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- **Docker** or **Podman** (Dev Containers uses Docker by default, but can be configured for Podman)
- **AWS CLI** (for deployment)
- **Git**

### Option 1: VSCode with DevContainers (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd distributed_pipeline_example
   ```

2. **Open in VSCode:**
   ```bash
   code .
   ```

3. **Reopen in Dev Container:**
   - VSCode will prompt you to "Reopen in Container" (or click the popup)
   - Or use `Cmd+Shift+P` → "Dev Containers: Reopen in Container"

4. **Wait for container build:**
   - First build takes ~5-10 minutes
   - All dependencies, NeoVim with Mason LSP, and tools are pre-installed
   - Python packages are installed automatically via `postCreateCommand`

5. **Configure environment:**
   ```bash
   python scripts/configure_env.py
   ```
   This interactive script will:
   - Find existing configuration from environment variables
   - Present each configurable option with defaults
   - Allow you to modify values interactively
   - Back up and save your `.env` file

6. **Start local services (for development):**
   ```bash
   docker compose -f infra/tofu/rke2-local/docker-compose.yaml up -d
   ```
   
   Or use the manual setup:
   ```bash
   # Start MinIO (S3-compatible storage)
   docker run -d --name minio -p 9000:9000 -p 9001:9001 \
     -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
     minio/minio server /data --console-address ":9001"
   
   # Start PostgreSQL (for manifest store and MLflow)
   docker run -d --name postgres -p 5432:5432 \
     -e POSTGRES_USER=mlops -e POSTGRES_PASSWORD=mlops -e POSTGRES_DB=mlops \
     postgres:15
   
   # Start MLflow
   docker run -d --name mlflow -p 5000:5000 \
     -e MLFLOW_BACKEND_STORE_URI="postgresql://mlops:mlops@host.docker.internal:5432/mlops" \
     -e MLFLOW_ARTIFACT_ROOT=s3://mlflow-artifacts \
     -e AWS_ACCESS_KEY_ID=minioadmin \
     -e AWS_SECRET_ACCESS_KEY=minioadmin \
     -e MLFLOW_S3_ENDPOINT_URL=http://host.docker.internal:9000 \
     ghcr.io/mlflow/mlflow:latest
   ```

### Option 2: NeoVim + TMux (Command-Line Development)

If you prefer command-line editing with NeoVim and TMux:

1. **Start the Dev Container:**
   ```bash
   docker build -t imageml-dev .devcontainer
   docker run -it --privileged -v $(pwd):/workspace \
     -p 5000:5000 -p 9000:9000 -p 9001:9001 -p 8000:8000 \
     --add-host=host.docker.internal:host-gateway \
     imageml-dev bash
   ```

2. **Start TMux with NeoVim:**
   ```bash
   # Using the provided convenience script
   dev-start
   
   # Or manually
   tmux new-session -d -s dev "nvim"
   tmux split-window -h
   tmux split-window -v
   tmux attach -t dev
   ```

3. **NeoVim Features:**
   - **Mason LSP**: Type `:Mason` to install language servers
   - **Auto-complete**: Built-in via nvim-cmp
   - **Keybindings**:
     - `gd` - Go to definition
     - `gr` - Find references
     - `K` - Hover documentation
     - `<leader>rn` - Rename
     - `<Tab>` / `<S-Tab>` - Navigate completions

4. **TMux Keybindings:**
   - `Ctrl-a |` - Split horizontally
   - `Ctrl-a -` - Split vertically
   - `Ctrl-a h/j/k/l` - Navigate panes
   - `Ctrl-a r` - Reload config

5. **Personalize Your Setup:**
   If you want to add your own NeoVim configuration, themes, or additional tools, you can use the `--additional-features` flag with the Dev Containers CLI:

   ```bash
   # Create your features JSON file (see format below)
   cat > ~/.config/imageml-dev-features.json << 'EOF'
   {
     "features": {
       "ghcr.io/devcontainers/features/zellij:1": {}
     }
   }
   EOF

   # Build with your additional features
   devcontainer build \
     --workspace-folder /path/to/distributed_pipeline_example \
     --additional-features "$(cat ~/.config/imageml-dev-features.json)"
   ```

   See the [Dev Containers Feature](https://containers.dev/implementors/features/) documentation for available features and how to create custom ones. For more on the Dev Containers CLI, see the [Dev Containers CLI documentation](https://containers.dev/supporting#devcontainers-cli).

### Development Scripts

The `scripts/` directory contains utilities for development and deployment:

| Script | Purpose |
|--------|---------|
| `configure_env.py` | Interactive environment configuration |
| `setup.sh` | Initial project setup and dependency installation |
| `functional_test_harness.py` | Run functional tests against local S3/MLflow |

#### Using configure_env.py

```bash
# Full interactive mode (menu-driven)
python scripts/configure_env.py

# Quick configure specific variables
python scripts/configure_env.py --quick AWS_REGION S3_ENDPOINT

# Configure single category
python scripts/configure_env.py --category "Stage 1 - Ingest & Augment"

# Set single value
python scripts/configure_env.py --set AWS_REGION us-west-2
```

### Deploying to AWS (Staging/Production)

#### Prerequisites

1. **Configure AWS credentials:**
   ```bash
   aws configure
   # Or use IAM roles via aws-vault, SOPS, etc.
   ```

2. **Set environment variables:**
   ```bash
   export AWS_REGION=us-east-1
   export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
   ```

#### Deploy Infrastructure

Choose your target infrastructure variant:

**Option A: AWS EC2**
```bash
cd infra/tofu/aws
terraform init
terraform plan -var="aws_region=$AWS_REGION"
terraform apply -var="aws_region=$AWS_REGION"
```

**Option B: EKS (Kubernetes)**
```bash
cd infra/tofu/eks
terraform init
terraform plan -var="aws_region=$AWS_REGION" -var="cluster_name=imageml-prod"
terraform apply -var="aws_region=$AWS_REGION" -var="cluster_name=imageml-prod"
```

**Option C: OpenShift (ARO)**
```bash
cd infra/tofu/openshift
terraform init
terraform plan -var="aws_region=$AWS_REGION" \
  -var="azure_subscription_id=$AZURE_SUB_ID" \
  -var="azure_tenant_id=$AZURE_TENANT_ID"
terraform apply
```

#### Build and Push Container Images

The GitHub Actions workflow builds and pushes to ECR automatically on merge to main. For manual build:

```bash
# Set ECR registry
export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Build and push each stage
for stage in stage1 stage2 stage3 stage4; do
  docker build -t $ECR_REGISTRY/imageml-${stage}:latest -t $ECR_REGISTRY/imageml-${stage}:$(git rev-parse HEAD) ${stage}/
  docker push $ECR_REGISTRY/imageml-${stage}:latest
  docker push $ECR_REGISTRY/imageml-${stage}:$(git rev-parse HEAD)
done
```

#### Deploy Stages to Kubernetes (EKS)

```bash
# Update kubectl context
aws eks update-kubeconfig --name imageml-prod

# Deploy pipeline stages
kubectl apply -f infra/tofu/eks/k8s-manifests.yaml

# Or deploy via Helm (if configured)
helm install imageml-pipeline ./charts/pipeline
```

### Running Pipeline Stages

Once deployed, run stages via:

```bash
# Stage 1: Ingest and Augment
kubectl run -it --rm stage1 --image=$ECR_REGISTRY/imageml-stage1:latest -- \
  python -m stage1 --mode poll

# Stage 2: Normalize
kubectl run -it --rm stage2 --image=$ECR_REGISTRY/imageml-stage2:latest -- \
  python -m stage2 --mode poll --sizes "1080p,720p"

# Stage 3: Training (scheduled)
kubectl create job training-daily --image=$ECR_REGISTRY/imageml-stage3:latest -- \
  python -m stage3 --epochs 10

# Stage 4: Inference
kubectl run -it --rm stage4 --image=$ECR_REGISTRY/imageml-stage4:latest -- \
  python -m stage4 --mode server
```

## Local Development Environment

A developer and CI environment is required that does not depend on AWS:
- DevContainers environment using Podman
- RustFS as the local S3-compatible object store
- PostgreSQL container for manifest store backing services
- MLflow container for tracking and local registry behavior
- Podman-Docker compatibility and podman compose assumed

The intent is to enable local end-to-end tests:
- upload images into RustFS S3 bucket
- run Stage 1 and Stage 2 against the local endpoint
- run a minimal training launch and verify MLflow artifacts and metrics

## Summary of the Most Important Requirements
- NVMe staging is required for performance. Each compute node must be provisioned with configurable NVMe capacity.
- Stage 2 must be able to generate multiple normalized size variants per original image.
- Annotation conversion must support Label Studio Pro format and COCO using the Label Studio SDK converter.
- Manifest store is the system of record for dataset lineage and stage completion.
- Training launcher must be configurable for epochs, images per node, instance counts, instance types, and input bucket.
- IaC must include variants for AWS, EKS, OpenShift, and local RKE2.

## Repository Deliverables
This bundle contains specification documents that a multi-agent coding workflow can use to build the repository:
- PROJECT_SPEC.md: build specification for implementation
- ARCHITECTURE.md: target architecture including NVMe staging and environment variants
- AGENTS.md: recommended OpenCode multi-agent orchestration plan
- TEST_PLAN.md: functional and performance testing plan
