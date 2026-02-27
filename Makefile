.PHONY: help install test lint typecheck infra-validate setup

help:
	@echo "ImageML Pipeline - Makefile Commands"
	@echo "====================================="
	@echo "install        - Install all dependencies"
	@echo "test           - Run all tests"
	@echo "lint           - Run linting"
	@echo "typecheck      - Run type checking"
	@echo "setup          - Run setup script"
	@echo "infra-validate - Validate Terraform/OpenTofu configs"
	@echo "clean          - Clean up generated files"

install:
	bash scripts/setup.sh

test:
	pytest -v

lint:
	ruff check .

typecheck:
	mypy .

infra-validate:
	@echo "Validating AWS infrastructure..."
	@cd infra/tofu/aws && terraform init -backend=false && terraform validate
	@echo "Validating EKS infrastructure..."
	@cd infra/tofu/eks && terraform init -backend=false && terraform validate
	@echo "Validating OpenShift infrastructure..."
	@cd infra/tofu/openshift && terraform init -backend=false && terraform validate
	@echo "Validating RKE2-local infrastructure..."
	@cd infra/tofu/rke2-local && terraform init -backend=false && terraform validate

setup-local:
	cp .env.example .env
	@echo "Edit .env with your configuration"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
