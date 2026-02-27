#!/usr/bin/env python3
"""
Interactive environment configuration script for ImageML Pipeline.

This script helps configure environment variables by:
1. Finding existing values from $ENV, .env files, .env.template, .env.example
2. Presenting each variable interactively with found defaults
3. Allowing changes with stage-based navigation
4. Providing $EDITOR option for direct editing
5. Date-versioning old .env files before saving
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from dotenv import dotenv_values
except ImportError:
    print("Installing python-dotenv...")
    os.system("pip install python-dotenv -q")
    from dotenv import dotenv_values


SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_TEMPLATE = PROJECT_ROOT / ".env.template"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
GITIGNORE = PROJECT_ROOT / ".gitignore"


CONFIG_VARS = [
    # AWS Configuration
    {
        "key": "AWS_REGION",
        "default": "us-east-1",
        "description": "AWS region for S3 and other AWS services",
        "category": "AWS Configuration",
    },
    {
        "key": "AWS_ACCESS_KEY_ID",
        "default": "",
        "description": "AWS access key ID for authentication (or use IAM roles)",
        "category": "AWS Configuration",
    },
    {
        "key": "AWS_SECRET_ACCESS_KEY",
        "default": "",
        "description": "AWS secret access key (use IAM roles in production)",
        "category": "AWS Configuration",
    },

    # S3 Configuration
    {
        "key": "S3_ENDPOINT",
        "default": "http://localhost:9000",
        "description": "S3-compatible endpoint URL (use http://localhost:9000 for local MinIO/RustFS)",
        "category": "S3 Configuration",
    },

    # Pipeline Bucket Configuration
    {
        "key": "RAW_BUCKET",
        "default": "image-raw",
        "description": "S3 bucket for raw input images",
        "category": "Pipeline Buckets",
    },
    {
        "key": "AUGMENTED_BUCKET",
        "default": "image-augmented",
        "description": "S3 bucket for augmented images (Stage 1 output)",
        "category": "Pipeline Buckets",
    },
    {
        "key": "NORMALIZED_BUCKET",
        "default": "image-normalized",
        "description": "S3 bucket for normalized images (Stage 2 output)",
        "category": "Pipeline Buckets",
    },
    {
        "key": "TRAINING_BUCKET",
        "default": "image-training",
        "description": "S3 bucket for training data (Stage 3 input)",
        "category": "Pipeline Buckets",
    },
    {
        "key": "INFERENCE_INPUT_BUCKET",
        "default": "image-inference-input",
        "description": "S3 bucket for inference input images",
        "category": "Pipeline Buckets",
    },
    {
        "key": "HITL_BUCKET",
        "default": "image-hitl",
        "description": "S3 bucket for human-in-the-loop review (Stage 4 output)",
        "category": "Pipeline Buckets",
    },
    {
        "key": "OUTPUT_BUCKET",
        "default": "image-output",
        "description": "S3 bucket for final output",
        "category": "Pipeline Buckets",
    },
    {
        "key": "MANIFEST_STORE_BUCKET",
        "default": "manifest-store",
        "description": "S3 bucket for manifest store",
        "category": "Pipeline Buckets",
    },
    {
        "key": "MLFLOW_ARTIFACTS_BUCKET",
        "default": "mlflow-artifacts",
        "description": "S3 bucket for MLflow artifacts",
        "category": "Pipeline Buckets",
    },

    # NVMe Staging Configuration
    {
        "key": "NVME_ROOT",
        "default": "/mnt/nvme",
        "description": "Root directory for NVMe staging (local fast storage)",
        "category": "NVMe Staging",
    },
    {
        "key": "NVME_MIN_GB",
        "default": "100",
        "description": "Minimum free space required on NVMe in GB",
        "category": "NVMe Staging",
    },

    # MLflow Configuration
    {
        "key": "MLFLOW_TRACKING_URL",
        "default": "http://localhost:5000",
        "description": "MLflow tracking server URL",
        "category": "MLflow",
    },
    {
        "key": "MLFLOW_REGISTRY_URL",
        "default": "http://localhost:5000",
        "description": "MLflow model registry URL (usually same as tracking)",
        "category": "MLflow",
    },
    {
        "key": "MLFLOW_EXPERIMENT",
        "default": "image-ml-training",
        "description": "MLflow experiment name for training runs",
        "category": "MLflow",
    },

    # Stage 1 Configuration
    {
        "key": "STAGE1_MODE",
        "default": "poll",
        "description": "Stage 1 execution mode: 'poll' or 'event'",
        "category": "Stage 1 - Ingest & Augment",
    },
    {
        "key": "STAGE1_POLL_INTERVAL",
        "default": "60",
        "description": "Stage 1 polling interval in seconds",
        "category": "Stage 1 - Ingest & Augment",
    },
    {
        "key": "RAW_PREFIX",
        "default": "images/",
        "description": "S3 prefix for raw images in RAW_BUCKET",
        "category": "Stage 1 - Ingest & Augment",
    },
    {
        "key": "OUTPUT_PREFIX",
        "default": "augmented/",
        "description": "S3 prefix for augmented output",
        "category": "Stage 1 - Ingest & Augment",
    },

    # Stage 2 Configuration
    {
        "key": "NORMALIZE_SIZES",
        "default": "1080p,720p,800x600",
        "description": "Comma-separated sizes for normalization (e.g., 1080p,720p,800x600)",
        "category": "Stage 2 - Normalize & Resize",
    },
    {
        "key": "INPUT_PREFIX",
        "default": "augmented/",
        "description": "S3 prefix for Stage 2 input in AUGMENTED_BUCKET",
        "category": "Stage 2 - Normalize & Resize",
    },

    # Stage 3 Configuration
    {
        "key": "EPOCHS",
        "default": "10",
        "description": "Number of training epochs",
        "category": "Stage 3 - Training",
    },
    {
        "key": "IMAGES_PER_NODE",
        "default": "100",
        "description": "Number of images to use per node for training",
        "category": "Stage 3 - Training",
    },
    {
        "key": "INSTANCE_COUNT",
        "default": "1",
        "description": "Number of training instances",
        "category": "Stage 3 - Training",
    },
    {
        "key": "INSTANCE_TYPE",
        "default": "ml.m5.xlarge",
        "description": "EC2 instance type for training",
        "category": "Stage 3 - Training",
    },
    {
        "key": "TRAINING_PREFIX",
        "default": "normalized/",
        "description": "S3 prefix for training data in TRAINING_BUCKET",
        "category": "Stage 3 - Training",
    },

    # Stage 4 Configuration
    {
        "key": "MODEL_NAME",
        "default": "image-ml-model",
        "description": "Name of model in MLflow registry",
        "category": "Stage 4 - Inference",
    },
    {
        "key": "MODEL_STAGE",
        "default": "Production",
        "description": "Model stage to load (Production, Staging, etc.)",
        "category": "Stage 4 - Inference",
    },
    {
        "key": "METRICS_ENABLED",
        "default": "true",
        "description": "Enable Prometheus metrics",
        "category": "Stage 4 - Inference",
    },
    {
        "key": "METRICS_PORT",
        "default": "8000",
        "description": "Port for Prometheus metrics endpoint",
        "category": "Stage 4 - Inference",
    },

    # Pipeline Configuration
    {
        "key": "DATASET_ID",
        "default": "default",
        "description": "Dataset identifier for manifest store",
        "category": "Pipeline Configuration",
    },
    {
        "key": "MODE",
        "default": "poll",
        "description": "Default execution mode for stages: 'poll' or 'event'",
        "category": "Pipeline Configuration",
    },
    {
        "key": "POLL_INTERVAL",
        "default": "60",
        "description": "Default polling interval in seconds",
        "category": "Pipeline Configuration",
    },

    # Database Configuration (for manifest store)
    {
        "key": "MANIFEST_STORE_DB_URL",
        "default": "",
        "description": "PostgreSQL connection URL for manifest store (e.g., postgresql://user:pass@host:5432/db)",
        "category": "Database",
    },
    {
        "key": "MLFLOW_DB_URL",
        "default": "",
        "description": "PostgreSQL connection URL for MLflow backend store",
        "category": "Database",
    },
]


def get_current_value(key: str) -> Optional[str]:
    """Get value from current environment, .env, .env.template, or .env.example"""
    sources = [
        os.environ.get(key),
        ENV_FILE.exists() and dotenv_values(ENV_FILE).get(key),
        ENV_TEMPLATE.exists() and dotenv_values(ENV_TEMPLATE).get(key),
        ENV_EXAMPLE.exists() and dotenv_values(ENV_EXAMPLE).get(key),
    ]

    for value in sources:
        if value is not None and value != "":
            return value
    return None


def ensure_gitignore():
    """Ensure .env is in .gitignore"""
    if not GITIGNORE.exists():
        GITIGNORE.write_text("")

    content = GITIGNORE.read_text()
    if ".env" not in content:
        with open(GITIGNORE, "a") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write("# Environment files\n.env\n.env.*\n")
        print("Added .env to .gitignore")


def backup_env_file():
    """Create date-versioned backup of existing .env file"""
    if not ENV_FILE.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f".env.backup_{timestamp}"
    backup_path = PROJECT_ROOT / backup_name
    shutil.copy2(ENV_FILE, backup_path)
    print(f"Backed up existing .env to {backup_name}")
    return backup_name


def write_env_file(values: dict):
    """Write environment values to .env file"""
    lines = [
        "# ImageML Pipeline Environment Configuration",
        f"# Generated: {datetime.now().isoformat()}",
        "",
    ]

    current_category = None
    for var in CONFIG_VARS:
        if var.get("category") != current_category:
            current_category = var.get("category")
            lines.append(f"\n# === {current_category} ===\n")

        key = var["key"]
        value = values.get(key, "")
        lines.append(f"# {var['description']}")
        lines.append(f"{key}={value}\n")

    ENV_FILE.write_text("\n".join(lines))
    print(f"\nEnvironment saved to {ENV_FILE}")


def print_header(text: str):
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def print_stage_menu():
    print_header("ImageML Pipeline Configuration")
    print("\nSelect a configuration stage:")
    print("  1. AWS & S3 Configuration")
    print("  2. Pipeline Buckets")
    print("  3. NVMe Staging")
    print("  4. MLflow")
    print("  5. Stage 1 - Ingest & Augment")
    print("  6. Stage 2 - Normalize & Resize")
    print("  7. Stage 3 - Training")
    print("  8. Stage 4 - Inference")
    print("  9. Pipeline & Database Configuration")
    print("  0. Review All & Save")
    print("  E. Open $EDITOR for direct editing")
    print("  Q. Quit without saving")
    print("\n  Or enter a variable name to edit directly (e.g., AWS_REGION)")


def get_category_stage_map():
    return {
        "1": "AWS Configuration",
        "2": "Pipeline Buckets",
        "3": "NVMe Staging",
        "4": "MLflow",
        "5": "Stage 1 - Ingest & Augment",
        "6": "Stage 2 - Normalize & Resize",
        "7": "Stage 3 - Training",
        "8": "Stage 4 - Inference",
        "9": "Pipeline Configuration",
    }


def configure_category(category: str, values: dict) -> dict:
    """Configure variables for a specific category"""
    vars_to_configure = [v for v in CONFIG_VARS if v.get("category") == category]

    if not vars_to_configure:
        print(f"No variables found for category: {category}")
        return values

    print_header(f"Configuring: {category}")
    print(f"Press Enter to keep current/default value, or type new value.\n")

    for var in vars_to_configure:
        key = var["key"]
        current = values.get(key) or get_current_value(key) or var.get("default", "")
        description = var["description"]

        prompt = f"\n{description}\n[{key}]: "

        user_input = input(prompt).strip()

        if user_input:
            values[key] = user_input
            print(f"  → Set {key} = {user_input}")
        else:
            values[key] = current
            print(f"  → Keeping: {current}")

    return values


def review_all(values: dict) -> bool:
    """Review all configured values and ask to save"""
    print_header("Review All Configuration")

    current_category = None
    for var in CONFIG_VARS:
        cat = var.get("category")
        if cat != current_category:
            current_category = cat
            print(f"\n--- {cat} ---")

        key = var["key"]
        value = values.get(key, "")
        print(f"  {key} = {value}")

    print("\n" + "=" * 40)
    choice = input("Save these values to .env? [Y/n]: ").strip().lower()
    return choice in ("", "y", "yes")


def open_editor(values: dict) -> tuple:
    """Open $EDITOR with current values, return (values, should_save)"""
    import tempfile

    # Create temp file with current values
    temp_content = [
        "# Edit environment variables below. Save and exit to continue.",
        "# Lines starting with # are comments and won't be saved.",
        "# To cancel, exit without saving or add #CANCEL at the end.",
        "",
    ]

    current_category = None
    for var in CONFIG_VARS:
        cat = var.get("category")
        if cat != current_category:
            current_category = cat
            temp_content.append(f"\n# === {cat} ===")

        key = var["key"]
        value = values.get(key) or get_current_value(key) or var.get("default", "")
        temp_content.append(f"# {var['description']}")
        temp_content.append(f"{key}={value}")

    temp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False, encoding="utf-8"
    )
    temp_path = temp_file.name
    temp_file.write("\n".join(temp_content))
    temp_file.close()

    # Open editor
    editor = os.environ.get("EDITOR", "vim")
    print(f"\nOpening $EDITOR ({editor})...")
    print("Save and exit to continue, or exit without saving to cancel.")
    os.system(f"{editor} {temp_path}")

    # Read back
    new_values = values.copy()
    with open(temp_path, "r") as f:
        content = f.read()

    # Check for cancel
    if "#CANCEL" in content:
        os.unlink(temp_path)
        print("Edit cancelled.")
        return values, False

    # Parse values
    for line in content.split("\n"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            new_values[key.strip()] = value.strip()

    # Clean up
    os.unlink(temp_path)

    return new_values, True


def run_interactive(quick_vars: list = None):
    """Run interactive configuration flow"""
    values = {}

    # Load existing values
    for var in CONFIG_VARS:
        val = get_current_value(var["key"])
        if val:
            values[var["key"]] = val

    if quick_vars:
        # Quick mode - configure specific variables only
        for key in quick_vars:
            var_info = next((v for v in CONFIG_VARS if v["key"] == key), None)
            if var_info:
                current = values.get(key) or get_current_value(key) or var_info.get("default", "")
                user_input = input(f"{var_info['description']}\n[{key}] (default: {current}): ").strip()
                if user_input:
                    values[key] = user_input
                else:
                    values[key] = current
        write_env_file(values)
        return

    stage_map = get_category_stage_map()
    modified = False

    while True:
        print_stage_menu()

        choice = input("\nEnter choice: ").strip().lower()

        if choice == "q":
            if modified:
                confirm = input("You have unsaved changes. Quit anyway? [y/N]: ").strip().lower()
                if confirm not in ("y", "yes"):
                    continue
            print("\nExiting without saving.")
            return

        elif choice == "e":
            values, should_save = open_editor(values)
            if should_save:
                modified = True
                backup_env_file()
                ensure_gitignore()
                write_env_file(values)
                print("Environment saved via $EDITOR")
                return
            continue

        elif choice == "0":
            if review_all(values):
                backup_env_file()
                ensure_gitignore()
                write_env_file(values)
                print("\n✓ Configuration saved successfully!")
                return
            continue

        elif choice in stage_map:
            old_values = values.copy()
            values = configure_category(stage_map[choice], values)
            if values != old_values:
                modified = True

        elif choice:
            # Try as variable name
            var_info = next((v for v in CONFIG_VARS if v["key"].lower() == choice.lower()), None)
            if var_info:
                current = values.get(var_info["key"]) or get_current_value(var_info["key"]) or var_info.get("default", "")
                user_input = input(f"{var_info['description']}\n[{var_info['key']}] (default: {current}): ").strip()
                if user_input:
                    values[var_info["key"]] = user_input
                    modified = True
                else:
                    values[var_info["key"]] = current
            else:
                print(f"Unknown option: {choice}")


def main():
    parser = argparse.ArgumentParser(
        description="Interactive environment configuration for ImageML Pipeline"
    )
    parser.add_argument(
        "--quick",
        nargs="+",
        help="Quick mode: configure specific variables (e.g., --quick AWS_REGION S3_ENDPOINT)",
    )
    parser.add_argument(
        "--category",
        choices=list(get_category_stage_map().values()),
        help="Configure a specific category only",
    )
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("KEY", "VALUE"),
        help="Set a specific variable non-interactively",
    )
    args = parser.parse_args()

    if args.set:
        # Non-interactive set
        key, value = args.set
        ensure_gitignore()

        # Load existing
        values = {}
        for var in CONFIG_VARS:
            val = get_current_value(var["key"])
            if val:
                values[var["key"]] = val

        values[key] = value
        backup_env_file()
        write_env_file(values)
        print(f"Set {key} = {value}")
        return

    if args.category:
        # Configure single category
        values = {}
        for var in CONFIG_VARS:
            val = get_current_value(var["key"])
            if val:
                values[var["key"]] = val
        configure_category(args.category, values)
        backup_env_file()
        ensure_gitignore()
        write_env_file(values)
        return

    run_interactive(quick_vars=args.quick)


if __name__ == "__main__":
    main()
