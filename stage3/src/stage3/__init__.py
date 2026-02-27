import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import mlflow
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.transforms as transforms
from torch.utils.data import DataLoader, Dataset
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from pipeline_common.s3 import S3Client, S3Config
from pipeline_common.nvme import NVMeStaging, NVMeConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Stage3Config:
    def __init__(self):
        self.training_bucket = os.getenv("TRAINING_BUCKET", "image-training")
        self.training_prefix = os.getenv("TRAINING_PREFIX", "normalized/")
        self.dataset_id = os.getenv("DATASET_ID", "default")
        self.epochs = int(os.getenv("EPOCHS", "10"))
        self.images_per_node = int(os.getenv("IMAGES_PER_NODE", "100"))
        self.instance_count = int(os.getenv("INSTANCE_COUNT", "1"))
        self.instance_type = os.getenv("INSTANCE_TYPE", "ml.m5.xlarge")
        self.mlflow_tracking_url = os.getenv("MLFLOW_TRACKING_URL", "http://localhost:5000")
        self.mlflow_registry_url = os.getenv("MLFLOW_REGISTRY_URL", "http://localhost:5000")
        self.mlflow_experiment = os.getenv("MLFLOW_EXPERIMENT", "image-ml-training")
        self.nvme_root = os.getenv("NVME_ROOT", "/mnt/nvme")
        self.s3_endpoint = os.getenv("S3_ENDPOINT")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")


class SimpleCNN(nn.Module):
    def __init__(self, num_classes: int = 10):
        super(SimpleCNN, self).__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 28 * 28, 256),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x


class ImageDataset(Dataset):
    def __init__(self, image_paths: list[Path], transform=None):
        self.image_paths = image_paths
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img_path = self.image_paths[idx]
        try:
            image = Image.open(img_path).convert("RGB")
            if self.transform:
                image = self.transform(image)
            label = 0
            return image, label
        except Exception as e:
            logger.warning(f"Error loading {img_path}: {e}")
            return torch.zeros(3, 224, 224), 0


class Stage3Trainer:
    def __init__(self, config: Stage3Config):
        self.config = config
        s3_config = S3Config(
            endpoint_url=config.s3_endpoint,
            region=config.aws_region,
            access_key=config.aws_access_key,
            secret_key=config.aws_secret_key,
        )
        self.s3_client = S3Client(s3_config)
        self.nvme = NVMeStaging(NVMeConfig(root=config.nvme_root))
        self._setup_mlflow()

    def _setup_mlflow(self) -> None:
        mlflow.set_tracking_uri(self.config.mlflow_tracking_url)
        mlflow.set_experiment(self.config.mlflow_experiment)

    def download_training_data(self) -> list[Path]:
        logger.info(f"Downloading training data from {self.config.training_bucket}/{self.config.training_prefix}")
        objects = self.s3_client.list_objects(
            self.config.training_bucket, self.config.training_prefix
        )
        image_paths = []
        
        for obj in objects:
            if obj["Key"].endswith((".jpg", ".png", ".jpeg")):
                local_path = self.nvme.get_input_path(Path(obj["Key"]).name)
                self.s3_client.download_file(
                    self.config.training_bucket, obj["Key"], str(local_path)
                )
                image_paths.append(local_path)
        
        logger.info(f"Downloaded {len(image_paths)} images")
        return image_paths

    def train(self) -> str:
        mlflow.start_run()
        mlflow.log_param("epochs", self.config.epochs)
        mlflow.log_param("images_per_node", self.config.images_per_node)
        mlflow.log_param("instance_count", self.config.instance_count)
        mlflow.log_param("instance_type", self.config.instance_type)

        image_paths = self.download_training_data()
        if not image_paths:
            logger.warning("No training images found")
            return ""

        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        dataset = ImageDataset(image_paths[:self.config.images_per_node], transform)
        dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

        model = SimpleCNN()
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device)

        total_start = time.time()
        for epoch in range(self.config.epochs):
            epoch_start = time.time()
            model.train()
            running_loss = 0.0
            
            for batch_idx, (images, labels) in enumerate(dataloader):
                images, labels = images.to(device), labels.to(device)
                
                optimizer.zero_grad()
                outputs = model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()
                
                running_loss += loss.item()

            epoch_loss = running_loss / len(dataloader)
            epoch_time = time.time() - epoch_start
            
            mlflow.log_metric("epoch_loss", epoch_loss, step=epoch)
            mlflow.log_metric("epoch_time", epoch_time, step=epoch)
            mlflow.log_metric("images_per_second", len(dataset) / epoch_time, step=epoch)
            
            logger.info(f"Epoch {epoch+1}/{self.config.epochs} - Loss: {epoch_loss:.4f} - Time: {epoch_time:.2f}s")

        total_time = time.time() - total_start
        mlflow.log_metric("total_training_time", total_time)
        
        model_path = self.nvme.get_output_path("model.pt")
        torch.save(model.state_dict(), model_path)
        
        mlflow.pytorch.log_model(model, "model")
        
        model_uri = mlflow.get_artifact_uri("model")
        logger.info(f"Model saved to {model_uri}")
        
        try:
            mlflow.register_model(model_uri, "image-ml-model")
            logger.info("Model registered in MLflow registry")
        except Exception as e:
            logger.warning(f"Could not register model: {e}")
        
        mlflow.end_run()
        
        return model_uri


def main():
    parser = argparse.ArgumentParser(description="Stage 3: Training")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--images-per-node", type=int, default=None)
    args = parser.parse_args()

    config = Stage3Config()
    
    if args.epochs:
        config.epochs = args.epochs
    if args.images_per_node:
        config.images_per_node = args.images_per_node

    trainer = Stage3Trainer(config)
    model_uri = trainer.train()
    print(f"Training complete. Model URI: {model_uri}")


if __name__ == "__main__":
    main()
