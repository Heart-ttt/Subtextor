"""视觉检测器子包（FR-9）：统一接口 detect(image) -> list[Signal]，多实现可插拔。"""

from .base import Detector
from .factory import build_detector, build_nsfw_detector, build_qr_detector

__all__ = ["Detector", "build_detector", "build_qr_detector", "build_nsfw_detector"]
