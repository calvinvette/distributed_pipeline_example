terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
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

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "image-ml-cluster"
}

variable "node_instance_type" {
  description = "EKS node instance type"
  type        = string
  default     = "m5.xlarge"
}

variable "node_desired_capacity" {
  description = "Desired number of nodes"
  type        = number
  default     = 3
}

variable "node_max_capacity" {
  description = "Maximum number of nodes"
  type        = number
  default     = 5
}

variable "nvme_size_gb" {
  description = "Size of NVMe storage in GB per node"
  type        = number
  default     = 500
}

locals {
  bucket_prefix = var.project_name
}

data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "${var.project_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = data.aws_availability_zones.available.names
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "19.0.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.28"

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnets
  cluster_endpoint_public_access = true

  eks_managed_node_group_defaults = {
    ami_type       = "AL2_x86_64"
    instance_types = [var.node_instance_type]
  }

  eks_managed_node_groups = {
    pipeline-workers = {
      name = "pipeline-workers"

      instance_types = [var.node_instance_type]

      min_size     = var.node_desired_capacity
      max_size     = var.node_max_capacity
      desired_size = var.node_desired_capacity

      pre_bootstrap_user_data = base64encode(<<-EOF
          #!/bin/bash
          mkdir -p /mnt/nvme
          mkfs -t ext4 /dev/nvme0n1 || true
          mount /dev/nvme0n1 /mnt/nvme
          echo '/dev/nvme0n1 /mnt/nvme ext4 defaults,nofail 0 2' >> /etc/fstab
          EOF
      )

      labels = {
        workload = "pipeline"
      }
    }
  }
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

resource "kubernetes_namespace" "pipeline" {
  metadata {
    name = "image-ml-pipeline"
  }
}

resource "kubernetes_config_map" "nvme_config" {
  metadata {
    name      = "nvme-config"
    namespace = kubernetes_namespace.pipeline.metadata[0].name
  }

  data = {
    "nvme-root" = "/mnt/nvme"
  }
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
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
