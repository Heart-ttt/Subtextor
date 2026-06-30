"""二维码解码器（FR-2，免训练，替换只检测的 opencv_qr）。

检测 + **解码**：用 OpenCV 把二维码内容解出来。解出的 payload（常是 URL）：
  · 是 URL → 放进 Signal.meta["url"]，喂通道一信誉查询 + 喂 VLM 看目的地；
  · 非 URL（vCard / 纯文本 / 私有 scheme）→ Signal.meta["payload"]，通道一跳过。

二维码是**中性信号**（HC-2）：检出/解码只提升不确定性、转交 VLM，绝不单独定罪。
缺 OpenCV 时返回空信号（不崩，流水线把不确定性交给 VLM）。
"""

from __future__ import annotations

import re
from typing import List, Union

from ..imaging import load_image
from ..types import Signal
from .base import Detector

_URL_LIKE = re.compile(r"^(https?://|www\.|[a-z0-9-]+\.[a-z]{2,})", re.IGNORECASE)


class QRDecoder(Detector):
    name = "qr_decoder"

    def detect(self, image: Union[str, bytes]) -> List[Signal]:
        try:
            import cv2
            import numpy as np
        except ImportError:
            return []

        img = load_image(image)
        arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        detector = cv2.QRCodeDetector()
        try:
            ok, decoded, points, _ = detector.detectAndDecodeMulti(arr)
        except Exception:
            ok, decoded, points = False, [], None
        if not ok or points is None:
            return []

        signals: List[Signal] = []
        for i, quad in enumerate(points):
            xs = [float(p[0]) for p in quad]
            ys = [float(p[1]) for p in quad]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            payload = decoded[i] if i < len(decoded) else ""
            meta = {}
            if payload and _URL_LIKE.match(payload.strip()):
                meta["url"] = payload.strip()
            elif payload:
                meta["payload"] = payload.strip()  # 非 URL 载荷，通道一跳过
            signals.append(Signal(type="qrcode", confidence=0.9, bbox=bbox, meta=meta))
        return signals
