import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class NVMeConfig:
    root: str
    min_gb: float = 100.0


class NVMeStaging:
    def __init__(self, config: NVMeConfig):
        self.config = config
        self.root = Path(config.root)
        self._ensure_directories()

    @classmethod
    def from_env(cls) -> "NVMeStaging":
        config = NVMeConfig(
            root=os.getenv("NVME_ROOT", "/mnt/nvme"),
            min_gb=float(os.getenv("NVME_MIN_GB", "100.0")),
        )
        return cls(config)

    def _ensure_directories(self) -> None:
        for subdir in ["input", "work", "output", "cache"]:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)

    def get_input_path(self, filename: str) -> Path:
        return self.root / "input" / filename

    def get_work_path(self, filename: str) -> Path:
        return self.root / "work" / filename

    def get_output_path(self, filename: str) -> Path:
        return self.root / "output" / filename

    def get_cache_path(self, filename: str) -> Path:
        return self.root / "cache" / filename

    def copy_to_input(self, src: Path, filename: Optional[str] = None) -> Path:
        dst = self.get_input_path(filename or src.name)
        shutil.copy2(src, dst)
        return dst

    def copy_to_work(self, src: Path, filename: Optional[str] = None) -> Path:
        dst = self.get_work_path(filename or src.name)
        shutil.copy2(src, dst)
        return dst

    def move_to_output(self, src: Path, filename: Optional[str] = None) -> Path:
        dst = self.get_output_path(filename or src.name)
        shutil.move(str(src), str(dst))
        return dst

    def cleanup_input(self) -> None:
        self._cleanup_dir(self.root / "input")

    def cleanup_work(self) -> None:
        self._cleanup_dir(self.root / "work")

    def cleanup_output(self) -> None:
        self._cleanup_dir(self.root / "output")

    def _cleanup_dir(self, directory: Path) -> None:
        if directory.exists():
            for item in directory.iterdir():
                if item.is_file():
                    item.unlink()

    def get_disk_usage(self) -> dict:
        total, used, free = shutil.disk_usage(self.root)
        return {
            "total_gb": total / (1024**3),
            "used_gb": used / (1024**3),
            "free_gb": free / (1024**3),
        }

    def check_capacity(self) -> bool:
        usage = self.get_disk_usage()
        return usage["free_gb"] >= self.config.min_gb
