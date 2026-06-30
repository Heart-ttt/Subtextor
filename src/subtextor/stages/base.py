"""Stage 抽象接口与流水线上下文（§9）。

每一级实现 process(ctx) -> Optional[Result]：
  · 返回 Result  → 得出结论，流水线短路结束（如缓存命中、初筛判正常、VLM 精判）。
  · 返回 None    → 未能定论，把不确定性交给下一级（体现级联立意）。

PipelineContext 在各级之间携带共享中间产物（信号、OCR 文本、prompt 等）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from ..types import Post, Result, Signal


@dataclass
class PipelineContext:
    post: Post
    cfg: dict
    prompt_variant: str = "base"          # 运行时可切换的 prompt 侧重点（FR-6/FR-7）
    phash: Optional[str] = None
    signals: List[Signal] = field(default_factory=list)
    ocr_text: str = ""
    text_suspicion: float = 0.0
    notes: List[str] = field(default_factory=list)  # 各级累积的简短说明，便于解释


class Stage(ABC):
    name: str = "stage"

    @abstractmethod
    def process(self, ctx: PipelineContext) -> Optional[Result]:
        raise NotImplementedError
