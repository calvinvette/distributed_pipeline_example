import os
from dataclasses import dataclass
from typing import Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


@dataclass
class S3Config:
    endpoint_url: Optional[str] = None
    region: str = "us-east-1"
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    bucket: Optional[str] = None


class S3Client:
    def __init__(self, config: S3Config):
        self.config = config
        self.client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            region_name=config.region,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            config=Config(signature_version="s3v4"),
        )

    @classmethod
    def from_env(cls, bucket: Optional[str] = None) -> "S3Client":
        config = S3Config(
            endpoint_url=os.getenv("S3_ENDPOINT"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            bucket=bucket or os.getenv("S3_BUCKET"),
        )
        return cls(config)

    def upload_file(self, local_path: str, bucket: str, key: str) -> str:
        self.client.upload_file(local_path, bucket, key)
        return f"s3://{bucket}/{key}"

    def download_file(self, bucket: str, key: str, local_path: str) -> None:
        self.client.download_file(bucket, key, local_path)

    def list_objects(self, bucket: str, prefix: str = "") -> list[dict]:
        paginator = self.client.get_paginator("list_objects_v2")
        results = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            if "Contents" in page:
                results.extend(page["Contents"])
        return results

    def put_object(self, bucket: str, key: str, body: bytes) -> None:
        self.client.put_object(Bucket=bucket, Key=key, Body=body)

    def get_object(self, bucket: str, key: str) -> bytes:
        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def head_object(self, bucket: str, key: str) -> dict:
        return self.client.head_object(Bucket=bucket, Key=key)

    def object_exists(self, bucket: str, key: str) -> bool:
        try:
            self.head_object(bucket, key)
            return True
        except ClientError:
            return False

    def delete_object(self, bucket: str, key: str) -> None:
        self.client.delete_object(Bucket=bucket, Key=key)
