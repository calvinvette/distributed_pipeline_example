import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import albumentations as A
import boto3
import cv2
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from pipeline_common.s3 import S3Client, S3Config
from pipeline_common.nvme import NVMeStaging, NVMeConfig
from pipeline_common.manifest import ManifestStore
from pipeline_common.metrics import PipelineMetrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Stage1Config:
    def __init__(self):
        self.raw_bucket = os.getenv("RAW_BUCKET", "image-raw")
        self.augmented_bucket = os.getenv("AUGMENTED_BUCKET", "image-augmented")
        self.raw_prefix = os.getenv("RAW_PREFIX", "images/")
        self.output_prefix = os.getenv("OUTPUT_PREFIX", "augmented/")
        self.dataset_id = os.getenv("DATASET_ID", "default")
        self.mode = os.getenv("MODE", "polling")
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "60"))
        self.nvme_root = os.getenv("NVME_ROOT", "/mnt/nvme")
        self.s3_endpoint = os.getenv("S3_ENDPOINT")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.manifest_bucket = os.getenv("MANIFEST_STORE_BUCKET", "manifest-store")


def create_augmentation_pipeline() -> A.Compose:
    return A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.RandomBrightnessContrast(p=0.3),
            A.GaussNoise(p=0.2),
            A.Blur(blur_limit=3, p=0.1),
            A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.2, rotate_limit=15, p=0.3),
        ],
        bbox_params=A.BboxParams(format="coco", label_fields=["class_labels"]),
    )


def load_image(path: Path) -> tuple:
    img = cv2.imread(str(path))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def save_image(img, path: Path) -> None:
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(path), img_bgr)


class Stage1Processor:
    def __init__(self, config: Stage1Config):
        self.config = config
        s3_config = S3Config(
            endpoint_url=config.s3_endpoint,
            region=config.aws_region,
            access_key=config.aws_access_key,
            secret_key=config.aws_secret_key,
        )
        self.s3_client = S3Client(s3_config)
        self.nvme = NVMeStaging(NVMeConfig(root=config.nvme_root))
        self.manifest_store = ManifestStore(self.s3_client, config.manifest_bucket)
        self.metrics = PipelineMetrics.from_env("stage1")
        self.augmentation = create_augmentation_pipeline()

    def process_object(self, s3_key: str) -> Optional[dict]:
        start_time = time.time()
        local_input = self.nvme.get_input_path(Path(s3_key).name)
        
        try:
            logger.info(f"Downloading {s3_key} to {local_input}")
            self.s3_client.download_file(
                self.config.raw_bucket, s3_key, str(local_input)
            )

            img = load_image(local_input)
            h, w = img.shape[:2]

            bboxes = []
            class_labels = []
            ann_path = local_input.with_suffix(".json")
            if ann_path.exists():
                with open(ann_path) as f:
                    annotations = json.load(f)
                    for ann in annotations.get("annotations", []):
                        bbox = ann.get("bbox", [])
                        if len(bbox) == 4:
                            bboxes.append(bbox)
                            class_labels.append(ann.get("category_id", 1))

            if bboxes:
                transformed = self.augmentation(
                    image=img, bboxes=bboxes, class_labels=class_labels
                )
                img = transformed["image"]
            else:
                transformed = self.augmentation(image=img)
                img = transformed["image"]

            output_filename = f"{Path(s3_key).stem}_aug{Path(s3_key).suffix}"
            output_path = self.nvme.get_output_path(output_filename)
            save_image(img, output_path)

            output_key = f"{self.config.output_prefix}{output_filename}"
            self.s3_client.upload_file(
                str(output_path), self.config.augmented_bucket, output_key
            )

            duration = time.time() - start_time
            self.metrics.record_duration("stage1", "success", duration)
            self.metrics.record_processed("stage1", "success")

            result = {
                "source_uri": f"s3://{self.config.raw_bucket}/{s3_key}",
                "output_uri": f"s3://{self.config.augmented_bucket}/{output_key}",
                "width": img.shape[1],
                "height": img.shape[0],
                "augmented": True,
            }
            logger.info(f"Processed {s3_key} -> {output_key}")
            return result

        except Exception as e:
            logger.error(f"Error processing {s3_key}: {e}")
            self.metrics.record_duration("stage1", "failed", time.time() - start_time)
            self.metrics.record_failed("stage1", str(e))
            return None
        finally:
            if local_input.exists():
                local_input.unlink()

    def poll_for_work(self) -> None:
        logger.info(f"Polling for new objects in {self.config.raw_bucket}/{self.config.raw_prefix}")
        processed_keys = set()
        
        while True:
            objects = self.s3_client.list_objects(
                self.config.raw_bucket, self.config.raw_prefix
            )
            new_objects = [
                obj["Key"]
                for obj in objects
                if obj["Key"] not in processed_keys and obj["Key"].endswith((".jpg", ".png", ".jpeg"))
            ]
            
            for s3_key in new_objects:
                if not self.manifest_store.is_processed(
                    self.config.dataset_id, 1, s3_key
                ):
                    result = self.process_object(s3_key)
                    if result:
                        self.manifest_store.mark_processed(
                            self.config.dataset_id, 1, s3_key
                        )
                    processed_keys.add(s3_key)

            time.sleep(self.config.poll_interval)

    def run_once(self, s3_keys: list[str]) -> list[dict]:
        results = []
        for s3_key in s3_keys:
            result = self.process_object(s3_key)
            if result:
                results.append(result)
                self.manifest_store.mark_processed(self.config.dataset_id, 1, s3_key)
        return results


def main():
    parser = argparse.ArgumentParser(description="Stage 1: Ingest and Augment")
    parser.add_argument("--mode", choices=["poll", "once"], default="poll")
    parser.add_argument("--keys", nargs="*", help="S3 keys to process in once mode")
    args = parser.parse_args()

    config = Stage1Config()
    processor = Stage1Processor(config)

    if args.mode == "poll":
        processor.poll_for_work()
    elif args.mode == "once" and args.keys:
        results = processor.run_once(args.keys)
        print(json.dumps(results, indent=2))
    else:
        logger.error("Please provide --keys when using once mode")
        sys.exit(1)


if __name__ == "__main__":
    main()
