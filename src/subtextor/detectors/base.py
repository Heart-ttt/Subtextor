"""检测器统一接口（FR-9 / HC-2）。

语义等价 detect(image) -> list[Signal]，Signal = {type, bbox, confidence}。
ONNX / opencv / 未来 YOLO 都实现这个接口，按 config 切换。

立意约束（HC-2）：检测器只"抽取信号"提升不确定性、转交 VLM，
绝不单独作为定罪依据。任何"检测到二维码就拦"的用法都违背立意。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Union

from ..types import Signal


class Detector(ABC):
    """视觉检测器抽象基类。"""

    name: str = "detector"

    @abstractmethod
    def detect(self, image: Union[str, bytes]) -> List[Signal]:
        """检测图中"值得 VLM 关注"的中性视觉信号，返回 Signal 列表（可为空）。"""
        raise NotImplementedError
