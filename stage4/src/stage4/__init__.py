import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import mlflow
import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms as transforms
from dotenv import load_dotenv
from flask import Flask, Response
from PIL import Image
from prometheus_client import Counter, Histogram, generate_latest

load_dotenv()

from pipeline_common.s3 import S3Client, S3Config
from pipeline_common.nvme import NVMeStaging, NVMeConfig
from pipeline_common.metrics import PipelineMetrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

INFERENCE_REQUESTS = Counter("inference_requests_total", "Total inference requests", ["status"])
INFERENCE_DURATION = Histogram("inference_duration_seconds", "Inference duration in seconds")


class Stage4Config:
    def __init__(self):
        self.input_bucket = os.getenv("INFERENCE_INPUT_BUCKET", "image-inference-input")
        self.hitl_bucket = os.getenv("HITL_BUCKET", "image-hitl")
        self.output_bucket = os.getenv("OUTPUT_BUCKET", "image-output")
        self.input_prefix = os.getenv("INPUT_PREFIX", "inference/")
        self.output_prefix = os.getenv("OUTPUT_PREFIX", "predictions/")
        self.dataset_id = os.getenv("DATASET_ID", "default")
        self.mode = os.getenv("MODE", "poll")
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "60"))
        self.nvme_root = os.getenv("NVME_ROOT", "/mnt/nvme")
        self.mlflow_tracking_url = os.getenv("MLFLOW_TRACKING_URL", "http://localhost:5000")
        self.mlflow_registry_url = os.getenv("MLFLOW_REGISTRY_URL", "http://localhost:5000")
        self.model_name = os.getenv("MODEL_NAME", "image-ml-model")
        self.model_stage = os.getenv("MODEL_STAGE", "Production")
        self.s3_endpoint = os.getenv("S3_ENDPOINT")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.metrics_port = int(os.getenv("METRICS_PORT", "8000"))


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


class Stage4Inference:
    def __init__(self, config: Stage4Config):
        self.config = config
        s3_config = S3Config(
            endpoint_url=config.s3_endpoint,
            region=config.aws_region,
            access_key=config.aws_access_key,
            secret_key=config.aws_secret_key,
        )
        self.s3_client = S3Client(s3_config)
        self.nvme = NVMeStaging(NVMeConfig(root=config.nvme_root))
        self.metrics = PipelineMetrics.from_env("stage4")
        self.model = None
        self.model_version = None
        self._load_model()

    def _load_model(self) -> None:
        mlflow.set_tracking_uri(self.config.mlflow_tracking_url)
        
        try:
            model_uri = f"models:/{self.config.model_name}/{self.config.model_stage}"
            self.model = mlflow.pytorch.load_model(model_uri)
            self.model.eval()
            self.model_version = self.model_stage
            logger.info(f"Loaded model from {model_uri}")
        except Exception as e:
            logger.warning(f"Could not load model from registry: {e}. Using stub model.")
            self.model = SimpleCNN()
            self.model.eval()
            self.model_version = "stub"

    def preprocess_image(self, img: np.ndarray) -> torch.Tensor:
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        pil_img = Image.fromarray(img)
        return transform(pil_img).unsqueeze(0)

    def predict(self, image_tensor: torch.Tensor) -> dict:
        with torch.no_grad():
            output = self.model(image_tensor)
            probabilities = torch.softmax(output, dim=1)
            predicted_class = torch.argmax(probabilities, dim=1).item()
            confidence = probabilities[0][predicted_class].item()
            
        return {
            "class_id": predicted_class,
            "confidence": confidence,
            "class_name": f"class_{predicted_class}",
        }

    def generate_coco_annotations(
        self, image_id: int, predictions: list[dict], image_width: int, image_height: int
    ) -> dict:
        annotations = {
            "images": [{
                "id": image_id,
                "width": image_width,
                "height": image_height,
            }],
            "categories": [
                {"id": i, "name": f"class_{i}"} for i in range(10)
            ],
            "annotations": [],
        }
        
        for pred in predictions:
            if pred.get("bbox"):
                x, y, w, h = pred["bbox"]
                annotations["annotations"].append({
                    "id": len(annotations["annotations"]) + 1,
                    "image_id": image_id,
                    "category_id": pred["class_id"],
                    "bbox": [x, y, w, h],
                    "area": w * h,
                    "iscrowd": 0,
                })
        
        return annotations

    def process_object(self, s3_key: str) -> Optional[dict]:
        start_time = time.time()
        local_input = self.nvme.get_input_path(Path(s3_key).name)
        
        try:
            logger.info(f"Downloading {s3_key} to {local_input}")
            self.s3_client.download_file(
                self.config.input_bucket, s3_key, str(local_input)
            )

            img = cv2.imread(str(local_input))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            image_tensor = self.preprocess_image(img)
            prediction = self.predict(image_tensor)
            
            height, width = img.shape[:2]
            predictions = [{
                "class_id": prediction["class_id"],
                "class_name": prediction["class_name"],
                "confidence": prediction["confidence"],
                "bbox": [width * 0.1, height * 0.1, width * 0.8, height * 0.8],
            }]
            
            coco_annotations = self.generate_coco_annotations(
                1, predictions, width, height
            )
            
            annotation_filename = f"{Path(s3_key).stem}_predictions.json"
            annotation_path = self.nvme.get_output_path(annotation_filename)
            
            with open(annotation_path, "w") as f:
                json.dump(coco_annotations, f, indent=2)
            
            annotation_key = f"{self.config.output_prefix}{annotation_filename}"
            self.s3_client.upload_file(
                str(annotation_path), self.config.hitl_bucket, annotation_key
            )
            
            hitl_key = f"hitl/{Path(s3_key).name}"
            self.s3_client.upload_file(
                str(local_input), self.config.hitl_bucket, hitl_key
            )

            duration = time.time() - start_time
            self.metrics.record_duration("stage4", "success", duration)
            self.metrics.record_processed("stage4", "success")
            self.metrics.record_prediction(self.model_version, prediction["class_name"])

            result = {
                "source_uri": f"s3://{self.config.input_bucket}/{s3_key}",
                "prediction_uri": f"s3://{self.config.hitl_bucket}/{annotation_key}",
                "hitl_uri": f"s3://{self.config.hitl_bucket}/{hitl_key}",
                "predictions": predictions,
            }
            logger.info(f"Processed {s3_key} -> predictions generated")
            return result

        except Exception as e:
            logger.error(f"Error processing {s3_key}: {e}")
            self.metrics.record_duration("stage4", "failed", time.time() - start_time)
            self.metrics.record_failed("stage4", str(e))
            return None
        finally:
            if local_input.exists():
                local_input.unlink()

    def poll_for_work(self) -> None:
        logger.info(f"Polling for new objects in {self.config.input_bucket}/{self.config.input_prefix}")
        
        while True:
            objects = self.s3_client.list_objects(
                self.config.input_bucket, self.config.input_prefix
            )
            new_objects = [
                obj["Key"]
                for obj in objects
                if obj["Key"].endswith((".jpg", ".png", ".jpeg"))
            ]
            
            for s3_key in new_objects:
                self.process_object(s3_key)

            time.sleep(self.poll_interval)


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype="text/plain")


@app.route("/health")
def health():
    return {"status": "healthy", "model_version": "stub"}


def main():
    parser = argparse.ArgumentParser(description="Stage 4: Inference and Auto-Annotation")
    parser.add_argument("--mode", choices=["poll", "server"], default="poll")
    args = parser.parse_args()

    config = Stage4Config()
    inference = Stage4Inference(config)

    if args.mode == "poll":
        inference.poll_for_work()
    elif args.mode == "server":
        logger.info(f"Starting metrics server on port {config.metrics_port}")
        app.run(host="0.0.0.0", port=config.metrics_port)


if __name__ == "__main__":
    main()
