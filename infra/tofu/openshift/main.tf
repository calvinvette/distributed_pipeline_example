terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "image-ml"
}

variable "openshift_cluster_name" {
  description = "OpenShift cluster name"
  type        = string
  default     = "image-ml-aro"
}

variable "worker_instance_type" {
  description = "Worker node instance type"
  type        = string
  default     = "m5.xlarge"
}

variable "worker_count" {
  description = "Number of worker nodes"
  type        = number
  default     = 3
}

variable "nvme_size_gb" {
  description = "Size of NVMe storage in GB"
  type        = number
  default     = 500
}

variable "aro_service_principal" {
  description = "Azure service principal app ID"
  type        = string
  sensitive   = true
}

variable "aro_service_principal_secret" {
  description = "Azure service principal password"
  type        = string
  sensitive   = true
}

variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "azure_tenant_id" {
  description = "Azure tenant ID"
  type        = string
}

variable "azure_resource_group" {
  description = "Azure resource group name"
  type        = string
  default     = "image-ml-rg"
}

locals {
  bucket_prefix = var.project_name
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_subnet" "private" {
  count             = 3
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 1}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.project_name}-private-subnet-${count.index}"
  }
}

resource "aws_iam_role" "openshift_cluster" {
  name = "${var.project_name}-aro-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_s3_bucket" "raw" {
  bucket = "${local.bucket_prefix}-raw"
}

resource "aws_s3_bucket" "augmented" {
  bucket = "${local.bucket_prefix}-augmented"
}

resource "aws_s3_bucket" "normalized" {
  bucket = "${local.bucket_prefix}-normalized"
}

resource "aws_s3_bucket" "training" {
  bucket = "${local.bucket_prefix}-training"
}

resource "aws_s3_bucket" "inference_input" {
  bucket = "${local.bucket_prefix}-inference-input"
}

resource "aws_s3_bucket" "hitl" {
  bucket = "${local.bucket_prefix}-hitl"
}

resource "aws_s3_bucket" "manifest_store" {
  bucket = "${local.bucket_prefix}-manifest-store"
}

resource "aws_s3_bucket" "mlflow_artifacts" {
  bucket = "${local.bucket_prefix}-mlflow-artifacts"
}

resource "aws_ecr_repository" "stage1" {
  name = "${var.project_name}-stage1"
}

resource "aws_ecr_repository" "stage2" {
  name = "${var.project_name}-stage2"
}

resource "aws_ecr_repository" "stage3" {
  name = "${var.project_name}-stage3"
}

resource "aws_ecr_repository" "stage4" {
  name = "${var.project_name}-stage4"
}

resource "null_resource" "openshift_cluster" {
  provisioner "local-exec" {
    command = <<-EOT
      echo "OpenShift cluster provisioning would be done via Azure CLI or RH API"
      echo "az aro create -g ${var.azure_resource_group} -n ${var.openshift_cluster_name}"
      echo ""
      echo "Worker node NVMe setup:"
      echo "  for node in $(oc get nodes -o jsonpath='{.items[*].metadata.name}'); do"
      echo "    oc debug node/$node -- chroot /host mkfs.ext4 /dev/nvme0n1"
      echo "    oc debug node/$node -- chroot /host mount /dev/nvme0n1 /mnt/nvme"
      echo "  done"
    EOT
  }
}

output "openshift_cluster_name" {
  value = var.openshift_cluster_name
}

output "s3_buckets" {
  value = {
    raw              = aws_s3_bucket.raw.id
    augmented        = aws_s3_bucket.augmented.id
    normalized       = aws_s3_bucket.normalized.id
    training         = aws_s3_bucket.training.id
    inference_input  = aws_s3_bucket.inference_input.id
    hitl             = aws_s3_bucket.hitl.id
    manifest_store   = aws_s3_bucket.manifest_store.id
    mlflow_artifacts = aws_s3_bucket.mlflow_artifacts.id
  }
}

output "ecr_repositories" {
  value = {
    stage1 = aws_ecr_repository.stage1.repository_url
    stage2 = aws_ecr_repository.stage2.repository_url
    stage3 = aws_ecr_repository.stage3.repository_url
    stage4 = aws_ecr_repository.stage4.repository_url
  }
}
