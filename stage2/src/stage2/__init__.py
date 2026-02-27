import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
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


class Stage2Config:
    def __init__(self):
        self.input_bucket = os.getenv("AUGMENTED_BUCKET", "image-augmented")
        self.output_bucket = os.getenv("NORMALIZED_BUCKET", "image-normalized")
        self.input_prefix = os.getenv("INPUT_PREFIX", "augmented/")
        self.output_prefix = os.getenv("OUTPUT_PREFIX", "normalized/")
        self.sizes = self._parse_sizes(os.getenv("NORMALIZE_SIZES", "1080p,720p"))
        self.dataset_id = os.getenv("DATASET_ID", "default")
        self.mode = os.getenv("MODE", "polling")
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "60"))
        self.nvme_root = os.getenv("NVME_ROOT", "/mnt/nvme")
        self.s3_endpoint = os.getenv("S3_ENDPOINT")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.manifest_bucket = os.getenv("MANIFEST_STORE_BUCKET", "manifest-store")

    def _parse_sizes(self, sizes_str: str) -> list[tuple[str, int, int]]:
        sizes = []
        for size in sizes_str.split(","):
            size = size.strip()
            if size == "1080p":
                sizes.append(("1080p", 1920, 1080))
            elif size == "720p":
                sizes.append(("720p", 1280, 720))
            elif size == "480p":
                sizes.append(("480p", 854, 480))
            elif "x" in size:
                parts = size.split("x")
                if len(parts) == 2:
                    sizes.append((size, int(parts[0]), int(parts[1])))
        return sizes


def resize_image(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    
    result = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    y_offset = (target_h - new_h) // 2
    x_offset = (target_w - new_w) // 2
    result[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
    
    return result


class Stage2Processor:
    def __init__(self, config: Stage2Config):
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
        self.metrics = PipelineMetrics.from_env("stage2")

    def process_object(self, s3_key: str) -> list[dict]:
        start_time = time.time()
        local_input = self.nvme.get_input_path(Path(s3_key).name)
        
        try:
            logger.info(f"Downloading {s3_key} to {local_input}")
            self.s3_client.download_file(
                self.config.input_bucket, s3_key, str(local_input)
            )

            img = cv2.imread(str(local_input))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            results = []
            for variant_name, target_w, target_h in self.config.sizes:
                resized = resize_image(img, target_w, target_h)
                
                variant_filename = f"{Path(s3_key).stem}_{variant_name}{Path(s3_key).suffix}"
                output_path = self.nvme.get_output_path(variant_filename)
                
                resized_bgr = cv2.cvtColor(resized, cv2.COLOR_RGB2BGR)
                cv2.imwrite(str(output_path), resized_bgr)

                output_key = f"{self.config.output_prefix}{variant_name}/{variant_filename}"
                self.s3_client.upload_file(
                    str(output_path), self.config.output_bucket, output_key
                )

                results.append({
                    "source_uri": f"s3://{self.config.input_bucket}/{s3_key}",
                    "variant_name": variant_name,
                    "output_uri": f"s3://{self.config.output_bucket}/{output_key}",
                    "width": target_w,
                    "height": target_h,
                })
                logger.info(f"Created variant {variant_name} -> {output_key}")

            duration = time.time() - start_time
            self.metrics.record_duration("stage2", "success", duration)
            self.metrics.record_processed("stage2", "success")
            
            return results

        except Exception as e:
            logger.error(f"Error processing {s3_key}: {e}")
            self.metrics.record_duration("stage2", "failed", time.time() - start_time)
            self.metrics.record_failed("stage2", str(e))
            return []
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
                if not self.manifest_store.is_processed(
                    self.config.dataset_id, 2, s3_key
                ):
                    results = self.process_object(s3_key)
                    if results:
                        self.manifest_store.publish_manifest(
                            self.config.dataset_id, 2, results
                        )
                        self.manifest_store.mark_processed(
                            self.config.dataset_id, 2, s3_key
                        )

            time.sleep(self.poll_interval)

    def run_once(self, s3_keys: list[str]) -> list[dict]:
        all_results = []
        for s3_key in s3_keys:
            results = self.process_object(s3_key)
            if results:
                all_results.extend(results)
                self.manifest_store.publish_manifest(
                    self.config.dataset_id, 2, results
                )
                self.manifest_store.mark_processed(
                    self.config.dataset_id, 2, s3_key
                )
        return all_results


def main():
    parser = argparse.ArgumentParser(description="Stage 2: Normalize and Resize")
    parser.add_argument("--mode", choices=["poll", "once"], default="poll")
    parser.add_argument("--keys", nargs="*", help="S3 keys to process in once mode")
    parser.add_argument(
        "--sizes",
        default=None,
        help="Comma-separated sizes (e.g., 1080p,720p,800x600)",
    )
    args = parser.parse_args()

    config = Stage2Config()
    if args.sizes:
        config.sizes = config._parse_sizes(args.sizes)

    processor = Stage2Processor(config)

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
