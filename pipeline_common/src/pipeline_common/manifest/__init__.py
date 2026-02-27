import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from pipeline_common.s3 import S3Client, S3Config


@dataclass
class DatasetManifest:
    dataset_id: str
    name: str
    created_at: datetime
    stage: int
    manifest_uri: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ObjectManifest:
    source_uri: str
    output_uri: str
    stage: int
    processed_at: datetime
    metadata: dict = field(default_factory=dict)


class ManifestStore:
    def __init__(self, s3_client: S3Client, bucket: str):
        self.s3 = s3_client
        self.bucket = bucket

    @classmethod
    def from_env(cls) -> "ManifestStore":
        s3_config = S3Config(
            endpoint_url=os.getenv("S3_ENDPOINT"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        s3_client = S3Client(s3_config)
        bucket = os.getenv("MANIFEST_STORE_BUCKET", "manifest-store")
        return cls(s3_client, bucket)

    def publish_manifest(
        self,
        dataset_id: str,
        stage: int,
        objects: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        manifest = {
            "dataset_id": dataset_id,
            "stage": stage,
            "timestamp": datetime.utcnow().isoformat(),
            "object_count": len(objects),
            "objects": objects,
            "metadata": metadata or {},
        }
        key = f"manifests/{dataset_id}/stage_{stage}/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        self.s3.put_object(self.bucket, key, json.dumps(manifest, indent=2).encode())
        return f"s3://{self.bucket}/{key}"

    def is_processed(self, dataset_id: str, stage: int, object_key: str) -> bool:
        prefix = f"processed/{dataset_id}/stage_{stage}/"
        objects = self.s3.list_objects(self.bucket, prefix)
        processed_keys = [obj["Key"] for obj in objects]
        return object_key in processed_keys

    def mark_processed(self, dataset_id: str, stage: int, object_key: str) -> None:
        key = f"processed/{dataset_id}/stage_{stage}/{object_key}.done"
        self.s3.put_object(self.bucket, key, b"")

    def get_latest_manifest(self, dataset_id: str, stage: int) -> Optional[dict]:
        prefix = f"manifests/{dataset_id}/stage_{stage}/"
        objects = self.s3.list_objects(self.bucket, prefix)
        if not objects:
            return None
        latest = sorted(objects, key=lambda x: x["LastModified"], reverse=True)[0]
        content = self.s3.get_object(self.bucket, latest["Key"])
        return json.loads(content)
