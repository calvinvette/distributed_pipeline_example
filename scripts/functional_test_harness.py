#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline_common" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "stage1" / "src"))

from dotenv import load_dotenv

load_dotenv()


class FunctionalTestHarness:
    def __init__(self, s3_endpoint: str = None):
        self.s3_endpoint = s3_endpoint or os.getenv("S3_ENDPOINT", "http://localhost:9000")
        self.results = []

    def test_nvme_staging(self, stage_module, stage_class, config):
        print("Testing NVMe staging...")
        from pipeline_common.nvme import NVMeStaging, NVMeConfig
        
        test_dir = Path("/tmp/test_nvme")
        test_dir.mkdir(exist_ok=True)
        
        nvme = NVMeStaging(NVMeConfig(root=str(test_dir)))
        
        test_file = test_dir / "input" / "test.txt"
        test_file.parent.mkdir(exist_ok=True)
        test_file.write_text("test content")
        
        result = nvme.check_capacity()
        
        self.results.append({
            "test": "nvme_staging",
            "passed": result,
            "details": f"Capacity check: {result}"
        })
        
        print(f"NVMe staging test: {'PASSED' if result else 'FAILED'}")
        return result

    def test_s3_pipeline(self):
        print("Testing S3 pipeline (Stage 1 + Stage 2)...")
        
        from pipeline_common.s3 import S3Client, S3Config
        
        s3_config = S3Config(
            endpoint_url=self.s3_endpoint,
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            secret_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        )
        
        client = S3Client(s3_config)
        
        bucket = "image-raw"
        
        test_content = b"test image content"
        test_key = "test/image_001.jpg"
        
        client.put_object(bucket, test_key, test_content)
        
        objects = client.list_objects(bucket, "test/")
        
        found = any(obj["Key"] == test_key for obj in objects)
        
        self.results.append({
            "test": "s3_pipeline",
            "passed": found,
            "details": f"Found test object: {found}"
        })
        
        print(f"S3 pipeline test: {'PASSED' if found else 'FAILED'}")
        return found

    def test_manifest_store(self):
        print("Testing manifest store...")
        
        from pipeline_common.s3 import S3Client, S3Config
        from pipeline_common.manifest import ManifestStore
        
        s3_config = S3Config(
            endpoint_url=self.s3_endpoint,
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            secret_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        )
        
        client = S3Client(s3_config)
        store = ManifestStore(client, "manifest-store")
        
        test_objects = [
            {"source_uri": "s3://bucket/key1.jpg", "output_uri": "s3://bucket/out1.jpg"},
            {"source_uri": "s3://bucket/key2.jpg", "output_uri": "s3://bucket/out2.jpg"},
        ]
        
        manifest_uri = store.publish_manifest("test_dataset", 1, test_objects)
        
        is_processed = store.is_processed("test_dataset", 1, "key1.jpg")
        
        self.results.append({
            "test": "manifest_store",
            "passed": manifest_uri is not None,
            "details": f"Manifest URI: {manifest_uri}, is_processed: {is_processed}"
        })
        
        print(f"Manifest store test: {'PASSED' if manifest_uri else 'FAILED'}")
        return manifest_uri is not None

    def run_all(self):
        print("=" * 60)
        print("Running Functional Tests")
        print("=" * 60)
        
        self.test_nvme_staging(None, None, {})
        self.test_s3_pipeline()
        self.test_manifest_store()
        
        print("\n" + "=" * 60)
        print("Test Results Summary")
        print("=" * 60)
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        for result in self.results:
            status = "PASSED" if result["passed"] else "FAILED"
            print(f"[{status}] {result['test']}: {result['details']}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        return passed == total


def main():
    parser = argparse.ArgumentParser(description="Run functional tests")
    parser.add_argument("--s3-endpoint", help="S3 endpoint URL")
    args = parser.parse_args()
    
    harness = FunctionalTestHarness(s3_endpoint=args.s3_endpoint)
    success = harness.run_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
