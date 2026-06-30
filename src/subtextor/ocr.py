"""图内文字 OCR 抽取（FR-2 / IB-4）。

图内文字不是输入字段，而是初筛层抽取的内部中间产物，与配文一起喂给 VLM。
默认 backend=null（返回空串），让最小 demo 无需安装 PaddleOCR 即可跑通；
配置 ocr: paddle 后启用中文 OCR。接口统一，可替换 easyocr / tesseract。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Union

from .imaging import load_image


class OCR(ABC):
    name = "ocr"

    @abstractmethod
    def extract(self, image: Union[str, bytes]) -> str:
        """抽取图内文字，返回纯文本（可为空串）。"""
        raise NotImplementedError


class NullOCR(OCR):
    """不做 OCR（默认）：返回空串，保证零依赖可跑。"""

    name = "null"

    def extract(self, image: Union[str, bytes]) -> str:
        return ""


class PaddleOCRBackend(OCR):
    """中文场景 OCR（PaddleOCR）。延迟初始化，仅在启用时加载重依赖。"""

    name = "paddle"

    def __init__(self, lang: str = "ch"):
        self.lang = lang
        self._engine = None
        self._degraded = False  # 缺库/初始化失败后降级，不再重试、不刷屏告警

    def _ensure(self) -> bool:
        if self._degraded:
            return False
        if self._engine is None:
            try:
                from paddleocr import PaddleOCR  # 重依赖，延迟导入

                self._engine = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
            except Exception as e:
                self._degraded = True
                print(f"[ocr] PaddleOCR 不可用，降级为不抽取图内文字（pip install paddleocr 可启用）：{e}")
                return False
        return True

    def extract(self, image: Union[str, bytes]) -> str:
        import numpy as np

        if not self._ensure():
            return ""  # 优雅降级：缺库时返回空串而非崩溃
        try:
            arr = np.array(load_image(image))
            result = self._engine.ocr(arr, cls=True)
        except Exception as e:
            print(f"[ocr] 抽取失败，跳过：{e}")
            return ""
        lines = []
        for page in result or []:
            for item in page or []:
                # item = [bbox, (text, score)]
                if item and len(item) >= 2 and item[1]:
                    lines.append(str(item[1][0]))
        return "\n".join(lines)


def build_ocr(cfg: dict) -> OCR:
    """按 config.prefilter.ocr 构建 OCR 后端。"""
    pf = cfg.get("prefilter", {})
    kind = pf.get("ocr") or "null"
    if kind == "paddle":
        return PaddleOCRBackend(lang=pf.get("ocr_lang", "ch"))
    # easyocr / tesseract 可在此扩展；默认 null。
    return NullOCR()
