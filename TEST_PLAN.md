# TEST_PLAN

This test plan focuses on functional validation of data distribution and staged execution, plus performance testing of training throughput.

## Test Categories
1. Unit tests
2. Functional tests
3. Performance tests
4. Smoke tests for infrastructure integration

## Unit Tests
Scope:
- Stage 1: augmentation logic, manifest generation schema
- Stage 2: resize and multi-variant mapping logic
- Stage 4: inference output schema and metrics endpoint behavior

Exclusions:
- Stage 3 training unit tests are not required, but training launcher input validation should have lightweight tests if practical.

## Functional Tests

### Functional Test 1: Local S3 Pipeline on RustFS
Goal:
- Validate Stage 1 and Stage 2 against a local S3-compatible endpoint.

Setup:
- Devcontainers environment with RustFS endpoint configured in env.
- Upload a small set of sample images to the local raw bucket.

Steps:
1. Run Stage 1 in polling mode with a test prefix.
2. Verify augmented outputs exist in the augmented bucket.
3. Verify Stage 1 manifest exists and includes source and output URIs.
4. Run Stage 2 with NORMALIZE_SIZES including multiple variants.
5. Verify normalized outputs exist under per-variant prefixes.
6. Verify Stage 2 manifest includes variant_name, width, height, and output URI.

Pass criteria:
- All expected objects exist.
- Manifests exist and pass schema validation.

### Functional Test 2: NVMe Staging Verification
Goal:
- Ensure each stage copies objects to local NVMe directories before processing.

Steps:
- Configure NVME_ROOT to a test directory.
- Run Stage 1 and Stage 2.
- Assert that:
  - input objects exist under NVME_ROOT/input
  - outputs are written to NVME_ROOT/output before upload
  - stage logs record the local paths used

Pass criteria:
- Evidence of local staging exists and matches the objects processed.

### Functional Test 3: Label Studio and COCO Conversion
Goal:
- Validate annotation conversion path using Label Studio SDK conversion utilities.

Steps:
- Provide a small Label Studio export JSON and matching images.
- Convert to COCO for training consumption.
- Convert COCO to Label Studio format for HITL workflows as needed.
- Validate converted artifacts are referenced by manifests.

Pass criteria:
- Conversion succeeds and outputs are referenced in manifests with correct annotation_format metadata.

### Functional Test 4: Minimal Training Execution and MLflow Artifacts
Goal:
- Validate that a training run can be launched and that MLflow captures artifacts.

Steps:
- Launch training in a minimal configuration (small dataset).
- Verify MLflow contains:
  - run parameters
  - at least one metric
  - a model artifact or placeholder artifact
  - a registered model entry or a stubbed registration record

Pass criteria:
- MLflow shows a completed run with artifacts and metadata.

## Performance Tests

### Performance Test 1: Training Throughput Scaling
Goal:
- Measure images per second and epoch duration as dataset size scales.

Parameters:
- dataset sizes: 10k, 50k, 200k images, or scaled-down equivalents in development
- images per node: configurable
- epochs: configurable
- number of instances: 1, 2, 4, 8 where available

Measurements:
- wall clock epoch time
- images per second
- GPU utilization if available
- data loader throughput and wait time where observable

Pass criteria:
- Tests produce repeatable measurements and store results, for example as CSV and MLflow artifacts.

### Performance Test 2: Stage 2 Multi-Variant Cost
Goal:
- Measure overhead of generating multiple variants.

Parameters:
- number of variants: 1, 2, 3, 5
- image sizes: mix of common resolutions

Measurements:
- images processed per second per variant
- total time per input image set
- NVMe write throughput and S3 upload throughput

Pass criteria:
- Measurements produced and stored.

## Smoke Tests for Infrastructure
- Terraform or OpenTofu validate and plan succeed for each variant.
- For AWS variant, verify resources exist:
  - buckets
  - ECR repos
  - schedules
  - optional queues

## Artifacts and Reporting
- Functional test logs stored as artifacts.
- Performance results stored:
  - as files in S3-compatible storage
  - and as MLflow artifacts when possible

## OpenCode Multi-Agent Execution Notes
- Assign one agent to implement test harness and scripts.
- Assign one agent to instrument stages for NVMe staging and metrics.
- Ensure tests are runnable locally in devcontainers with RustFS and MLflow.
