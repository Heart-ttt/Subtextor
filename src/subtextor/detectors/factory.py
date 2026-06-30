"""按配置构建检测器（FR-9）。

初筛层用两类检测器：
  · 中性信号检测器：二维码解码器（QRDecoder，检测+解码 URL）。
  · 确定性视觉检测器：L0 NSFW（NSFWDetector，高分硬拦），模型缺失时返回 None。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Detector


def build_qr_detector(cfg: dict) -> Detector:
    from .qr_decoder import QRDecoder

    return QRDecoder()


def build_nsfw_detector(cfg: dict) -> Optional[Detector]:
    nc = cfg.get("nsfw", {})
    if not nc.get("enabled", True):
        return None
    from ..config import resolve_path
    from .nsfw_onnx import NSFWDetector

    model_path = resolve_path(cfg, nc.get("model_path", "models/nsfw.onnx"))
    return NSFWDetector(
        str(model_path),
        input_size=nc.get("input_size", 224),
        nsfw_index=nc.get("nsfw_index", 1),
        nsfw_indices=nc.get("nsfw_indices"),
        output_kind=nc.get("output_kind", "softmax2"),
        normalize=nc.get("normalize", True),
        layout=nc.get("layout", "nchw"),
        rescale=nc.get("rescale", True),
    )


def build_detector(cfg: dict) -> Detector:
    """向后兼容入口（如 benchmark 的纯图像 baseline 用）：返回二维码检测器。"""
    return build_qr_detector(cfg)
