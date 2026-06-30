"""③ VLM 图文联合精判层 + ④ 三档分流的 VLM 部分（FR-3 / FR-4）。

只处理初筛升级上来的少数帖子；把图像与配文（含 OCR 抽出的图内文字）一起送 VLM，
输出 label + severity + reason，经 §4.3/§4.4 转为最终 Result（score 由 severity 映射，HC-7）。
"""

from __future__ import annotations

from typing import Optional

from ..prompts import get_prompt
from ..routing import map_vlm_decision
from ..types import Result, StageName
from ..vlm import build_vlm_backend
from .base import PipelineContext, Stage


class VLMStage(Stage):
    name = "vlm"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.backend = build_vlm_backend(cfg)

    def process(self, ctx: PipelineContext) -> Optional[Result]:
        prompt_text = get_prompt(ctx.prompt_variant)
        combined_text = "\n".join(t for t in (ctx.post.text, ctx.ocr_text) if t) or "（无配文）"

        vlm_result = self.backend.analyze(ctx.post.image, combined_text, prompt_text)
        score, decision = map_vlm_decision(vlm_result.label, vlm_result.severity, self.cfg)

        reason = vlm_result.reason
        if vlm_result.degraded:
            reason = f"[降级] {reason}"

        sev = vlm_result.severity.value if vlm_result.severity else "降级"
        ctx.notes.append(
            f"VLM：图文联合精判 → {vlm_result.label.value}/{sev} → {decision.value}"
        )

        return Result(
            label=vlm_result.label,
            score=score,
            reason=reason,
            decision=decision,
            stage=StageName.VLM,
            post_id=ctx.post.post_id,
            signals=ctx.signals,
            ocr_text=ctx.ocr_text,
            extra={
                "severity": vlm_result.severity.value if vlm_result.severity else None,
                "degraded": vlm_result.degraded,
                "prompt_variant": ctx.prompt_variant,
            },
        )
