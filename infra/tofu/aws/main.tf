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

variable "nvme_size_gb" {
  description = "Size of NVMe storage in GB"
  type        = number
  default     = 500
}

variable "instance_type" {
  description = "EC2 instance type for pipeline workers"
  type        = string
  default     = "m5.xlarge"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

locals {
  bucket_prefix = var.project_name
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
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

resource "aws_iam_role" "pipeline_worker" {
  name = "${var.project_name}-worker-role"

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

resource "aws_iam_policy" "s3_access" {
  name = "${var.project_name}-s3-access"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "s3_access" {
  role       = aws_iam_role.pipeline_worker.name
  policy_arn = aws_iam_policy.s3_access.arn
}

resource "aws_iam_instance_profile" "pipeline_worker" {
  name = "${var.project_name}-worker-profile"
  role = aws_iam_role.pipeline_worker.name
}

resource "aws_launch_template" "worker" {
  name = "${var.project_name}-worker-lt"

  iam_instance_profile {
    name = aws_iam_instance_profile.pipeline_worker.name
  }

  image_id      = "ami-0c55b159cbfafe1f0"
  instance_type = var.instance_type

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size = var.nvme_size_gb
      volume_type = "gp3"
    }
  }

  user_data = base64encode(<<-EOF
              #!/bin/bash
              mkdir -p /mnt/nvme
              mkfs -t ext4 /dev/nvme0n1 || true
              mount /dev/nvme0n1 /mnt/nvme
              echo '/dev/nvme0n1 /mnt/nvme ext4 defaults,nofail 0 2' >> /etc/fstab
              EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-worker"
    }
  }
}

resource "aws_instance" "worker" {
  count         = 1
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = var.instance_type
  subnet_id     = aws_subnet.public.id

  launch_template {
    id      = aws_launch_template.worker.id
    version = "$Latest"
  }

  tags = {
    Name = "${var.project_name}-worker-${count.index}"
  }
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

output "worker_instance_ids" {
  value = aws_instance.worker[*].id
}
