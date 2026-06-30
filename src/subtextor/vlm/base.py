"""VLM 后端抽象基类 + 三层结构化输出保证的编排（§4.3 / HC-6）。

子类只需实现 _chat(image, text, prompt_text, temperature) -> str（返回原始回复）。
三层机制（L1 在 prompt 内、L2 容错解析、L3 失败降级+重试）在本基类统一实现，
保证任何后端的 analyze() 都返回合法 VLMResult，失败时降级为"待人工"，绝不崩溃。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Union

from ..types import Label, VLMResult
from .parsing import parse_vlm_json


class VLMBackend(ABC):
    name = "vlm"

    def __init__(self, cfg: dict):
        vcfg = cfg.get("vlm", {})
        self.cfg = cfg
        self.temperature = float(vcfg.get("temperature", 0.2))
        self.retry_temperature = float(vcfg.get("retry_temperature", 0.0))
        self.max_tokens = int(vcfg.get("max_tokens", 512))
        self.model = vcfg.get("model", "")

    @abstractmethod
    def _chat(self, image: Union[str, bytes], text: str, prompt_text: str, temperature: float) -> str:
        """实际调用底层模型，返回原始文本回复。子类实现。"""
        raise NotImplementedError

    def analyze(self, image: Union[str, bytes], text: str, prompt_text: str) -> VLMResult:
        """图文联合精判，保证返回合法 VLMResult（§4.3 三层）。"""
        # 第一次：正常温度。
        try:
            raw = self._chat(image, text, prompt_text, self.temperature)
        except Exception as e:
            return self._degrade(f"VLM 调用异常：{e}")

        result = parse_vlm_json(raw)
        if result is not None:
            return result

        # L3：解析/校验失败 → 重试一次（降温度）。
        try:
            raw2 = self._chat(image, text, prompt_text, self.retry_temperature)
        except Exception as e:
            return self._degrade(f"VLM 重试调用异常：{e}", raw=raw)

        result = parse_vlm_json(raw2)
        if result is not None:
            return result

        # 仍失败 → 降级为待人工，绝不把脏数据漏给下游（HC-6）。
        return self._degrade("VLM 输出无法解析为合法结构化结果，降级人工复核", raw=raw2)

    @staticmethod
    def _degrade(reason: str, raw: str = None) -> VLMResult:
        return VLMResult(label=Label.NORMAL, severity=None, reason=reason, degraded=True, raw=raw)
