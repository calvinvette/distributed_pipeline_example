import os
from dataclasses import dataclass
from typing import Optional

try:
    from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry
    from prometheus_client import push_to_gateway as prometheus_push_to_gateway
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@dataclass
class MetricsConfig:
    enabled: bool = True
    push_gateway_url: Optional[str] = None
    job_name: str = "pipeline_stage"


class PipelineMetrics:
    def __init__(self, config: MetricsConfig):
        self.config = config
        if PROMETHEUS_AVAILABLE and config.enabled:
            self.registry = CollectorRegistry()
            self._setup_metrics()
        else:
            self.registry = None

    def _setup_metrics(self) -> None:
        if not self.registry:
            return
        self.stage_duration = Histogram(
            "pipeline_stage_duration_seconds",
            "Duration of pipeline stage in seconds",
            ["stage", "status"],
            registry=self.registry,
        )
        self.objects_processed = Counter(
            "pipeline_objects_processed_total",
            "Total number of objects processed",
            ["stage", "status"],
            registry=self.registry,
        )
        self.objects_failed = Counter(
            "pipeline_objects_failed_total",
            "Total number of objects that failed processing",
            ["stage", "reason"],
            registry=self.registry,
        )
        self.nvme_disk_usage = Gauge(
            "pipeline_nvme_disk_usage_gb",
            "NVMe disk usage in GB",
            ["type"],
            registry=self.registry,
        )
        self.inference_predictions = Counter(
            "pipeline_inference_predictions_total",
            "Total number of inference predictions",
            ["model_version", "class"],
            registry=self.registry,
        )

    def record_duration(self, stage: str, status: str, duration: float) -> None:
        if self.registry:
            self.stage_duration.labels(stage=stage, status=status).observe(duration)

    def record_processed(self, stage: str, status: str = "success") -> None:
        if self.registry:
            self.objects_processed.labels(stage=stage, status=status).inc()

    def record_failed(self, stage: str, reason: str) -> None:
        if self.registry:
            self.objects_failed.labels(stage=stage, reason=reason).inc()

    def update_disk_usage(self, total: float, used: float, free: float) -> None:
        if self.registry:
            self.nvme_disk_usage.labels(type="total").set(total)
            self.nvme_disk_usage.labels(type="used").set(used)
            self.nvme_disk_usage.labels(type="free").set(free)

    def record_prediction(self, model_version: str, class_name: str) -> None:
        if self.registry:
            self.inference_predictions.labels(
                model_version=model_version, class=class_name
            ).inc()

    def push_to_gateway(self) -> None:
        if self.config.push_gateway_url and self.registry:
            prometheus_push_to_gateway(
                self.config.push_gateway_url,
                job=self.config.job_name,
                registry=self.registry,
            )

    @classmethod
    def from_env(cls, stage: str = "unknown") -> "PipelineMetrics":
        config = MetricsConfig(
            enabled=os.getenv("METRICS_ENABLED", "true").lower() == "true",
            push_gateway_url=os.getenv("PUSH_GATEWAY_URL"),
            job_name=f"pipeline_{stage}",
        )
        return cls(config)
