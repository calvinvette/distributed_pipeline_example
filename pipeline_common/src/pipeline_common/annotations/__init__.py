import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from label_studio_sdk import LabelStudio
    from label_studio_sdk.converter import Converter
    LABEL_STUDIO_SDK_AVAILABLE = True
except ImportError:
    LABEL_STUDIO_SDK_AVAILABLE = False


@dataclass
class AnnotationConfig:
    format: str
    converter_version: Optional[str] = None


class AnnotationConverter:
    def __init__(self):
        if not LABEL_STUDIO_SDK_AVAILABLE:
            raise ImportError("label_studio_sdk is required for annotation conversion")

    def label_studio_to_coco(
        self, label_studio_json: list[dict], image_dir: Path, output_path: Path
    ) -> dict:
        converter = Converter(export_type="COCO")
        coco_data = converter.convert(
            label_studio_project=None,
            label_studio_tasks=label_studio_json,
            output_dir=str(output_path.parent),
            export_format="COCO",
        )
        return coco_data

    def coco_to_label_studio(
        self, coco_json: dict, images: list[str]
    ) -> list[dict]:
        ls_tasks = []
        coco_categories = coco_json.get("categories", [])
        for ann in coco_json.get("annotations", []):
            img_id = ann["image_id"]
            img_info = next((img for img in coco_json["images"] if img["id"] == img_id), None)
            if not img_info:
                continue
            task = {
                "data": {"image": f"<img>{images[img_id]}</img>"},
                "predictions": [
                    {
                        "result": self._coco_bbox_to_ls(ann, img_info, coco_categories),
                        "model_version": "coco-converter",
                    }
                ],
            }
            ls_tasks.append(task)
        return ls_tasks

    def _coco_bbox_to_ls(self, ann: dict, img_info: dict, coco_categories: list) -> list[dict]:
        bbox = ann.get("bbox", [])
        if not bbox:
            return []
        x, y, w, h = bbox
        category_name = coco_categories[ann["category_id"] - 1].get("name", "object") if ann["category_id"] <= len(coco_categories) else "object"
        return [
            {
                "id": f"bbox-{ann['id']}",
                "type": "rectanglelabels",
                "from_name": "label",
                "to_name": "image",
                "image_rotation": 0,
                "original_rotation": 0,
                "value": {
                    "rotation": 0,
                    "x": x / img_info["width"] * 100,
                    "y": y / img_info["height"] * 100,
                    "width": w / img_info["width"] * 100,
                    "height": h / img_info["height"] * 100,
                    "rectanglelabels": [category_name],
                },
            }
        ]


def load_annotations(path: Path, format: str) -> dict | list:
    with open(path) as f:
        if format == "json":
            return json.load(f)
        return json.load(f)


def save_annotations(data: dict | list, path: Path, format: str) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
