import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline_common" / "src"))


class TestS3Client:
    def test_s3_config_creation(self):
        from pipeline_common.s3 import S3Config
        config = S3Config(
            endpoint_url="http://localhost:9000",
            region="us-east-1",
            access_key="test",
            secret_key="test",
        )
        assert config.endpoint_url == "http://localhost:9000"
        assert config.region == "us-east-1"

    def test_nvme_staging(self):
        import tempfile
        from pipeline_common.nvme import NVMeStaging, NVMeConfig
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config = NVMeConfig(root=tmpdir)
            staging = NVMeStaging(config)
            
            assert staging.check_capacity() == True
            assert (Path(tmpdir) / "input").exists()
            assert (Path(tmpdir) / "work").exists()
            assert (Path(tmpdir) / "output").exists()


class TestManifestStore:
    def test_manifest_publish(self):
        from pipeline_common.s3 import S3Client, S3Config
        from pipeline_common.manifest import ManifestStore
        
        mock_s3 = Mock(spec=S3Client)
        store = ManifestStore(mock_s3, "test-bucket")
        
        objects = [
            {"source_uri": "s3://bucket/key1.jpg", "output_uri": "s3://bucket/out1.jpg"}
        ]
        
        result = store.publish_manifest("dataset1", 1, objects)
        
        assert "s3://test-bucket/" in result
        mock_s3.put_object.assert_called_once()


class TestAnnotationConverter:
    def test_coco_to_label_studio(self):
        from pipeline_common.annotations import AnnotationConverter
        
        converter = AnnotationConverter()
        
        coco_data = {
            "images": [{"id": 0, "width": 800, "height": 600, "file_name": "test.jpg"}],
            "annotations": [
                {"id": 1, "image_id": 0, "category_id": 1, "bbox": [100, 100, 200, 150]}
            ],
            "categories": [{"id": 1, "name": "car"}]
        }
        
        result = converter.coco_to_label_studio(coco_data, ["test.jpg"])
        
        assert len(result) > 0
        assert "data" in result[0]


class TestPipelineMetrics:
    def test_metrics_config(self):
        import os
        from pipeline_common.metrics import MetricsConfig, PipelineMetrics
        
        os.environ["METRICS_ENABLED"] = "false"
        
        config = MetricsConfig(enabled=False)
        metrics = PipelineMetrics(config)
        
        assert metrics.registry is None
