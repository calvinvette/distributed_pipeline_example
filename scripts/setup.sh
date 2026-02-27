#!/usr/bin/env bash
set -e

echo "ImageML Pipeline Setup Script"
echo "==============================="

echo "Checking for required tools..."
command -v uv >/dev/null 2>&1 || { echo "uv is required but not installed. Install: https://github.com/astral-sh/uv"; exit 1; }

echo "Setting up project directories..."
mkdir -p ~/.config/opencode

echo "Installing pipeline common library..."
cd pipeline_common
uv pip install -e ".[dev]"
cd ..

echo "Installing Stage 1..."
cd stage1
uv pip install -e ".[dev]"
cd ..

echo "Installing Stage 2..."
cd stage2
uv pip install -e ".[dev]"
cd ..

echo "Installing Stage 3..."
cd stage3
uv pip install -e ".[dev]"
cd ..

echo "Installing Stage 4..."
cd stage4
uv pip install -e ".[dev]"
cd ..

echo "Setting up pre-commit hooks..."
uv pip install pre-commit
pre-commit install

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and configure your environment"
echo "2. Run 'docker compose up -d' to start local services"
echo "3. Run 'python scripts/functional_test_harness.py' to test"
