"""四级级联流水线编排（§5.1 / FR-1~FR-4 / AC-1）。

设计原则：便宜的层扛流量，昂贵的 VLM 只处理模糊地带。
顺序执行 缓存 → 初筛 → VLM；任一级返回 Result 即短路结束。
高置信结论（clear/放行或拦截）写回缓存层（FR-4）。

并附带运行统计（NFR-2）：进入 VLM 的占比、各级延迟等，支撑 benchmark（AC-5）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from .config import load_config
from .stages.base import PipelineContext
from .stages.cache_stage import CacheStage
from .stages.prefilter_stage import PrefilterStage
from .stages.vlm_stage import VLMStage
from .types import Decision, Post, Result, StageName


@dataclass
class PipelineStats:
    """累计运行统计（NFR-2）。"""

    total: int = 0
    by_stage: dict = field(default_factory=lambda: {s.value: 0 for s in StageName})
    vlm_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    def record(self, result: Result) -> None:
        self.total += 1
        self.by_stage[result.stage.value] = self.by_stage.get(result.stage.value, 0) + 1
        if result.stage == StageName.VLM:
            self.vlm_count += 1
        self.latencies_ms.append(result.latency_ms)

    def summary(self) -> dict:
        n = max(self.total, 1)
        avg = sum(self.latencies_ms) / max(len(self.latencies_ms), 1)
        return {
            "total": self.total,
            "by_stage": self.by_stage,
            "vlm_ratio": round(self.vlm_count / n, 4),
            "avg_latency_ms": round(avg, 2),
        }


class Pipeline:
    """四级级联流水线。主逻辑与硬件/后端解耦（HC-5）：后端形态由 config 决定。"""

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = cfg or load_config()
        self.cache = CacheStage(self.cfg)
        self.prefilter = PrefilterStage(self.cfg)
        self.vlm = VLMStage(self.cfg)
        # 按 config.pipeline.stages 的顺序编排（默认 cache → prefilter → vlm）。
        registry = {"cache": self.cache, "prefilter": self.prefilter, "vlm": self.vlm}
        order = self.cfg.get("pipeline", {}).get("stages", ["cache", "prefilter", "vlm"])
        self.stages = [registry[name] for name in order if name in registry]
        self.stats = PipelineStats()

    def detect(self, post: Post, prompt_variant: str = None) -> Result:
        """对一个帖子跑完整级联，返回结构化 Result（语义等价 detect(post)->Result）。

        prompt_variant: 运行时切换的 prompt 侧重点；None 则用 config.vlm.prompt。
        """
        t0 = time.perf_counter()
        variant = prompt_variant or self.cfg.get("vlm", {}).get("prompt", "base")
        ctx = PipelineContext(post=post, cfg=self.cfg, prompt_variant=variant)

        result: Optional[Result] = None
        for stage in self.stages:
            result = stage.process(ctx)
            if result is not None:
                break

        if result is None:
            # 理论上 VLM 级总会给结论；兜底防御。
            from .types import Label

            result = Result(
                label=Label.NORMAL,
                score=0.0,
                reason="无任何级得出结论（异常兜底），转人工。",
                decision=Decision.REVIEW,
                stage=StageName.VLM,
                post_id=post.post_id,
            )

        result.latency_ms = (time.perf_counter() - t0) * 1000.0
        # 暴露各级轨迹（哪级决策/为什么），供审核台可视化。
        result.extra.setdefault("trace", list(ctx.notes))
        self.stats.record(result)
        self._maybe_cache(ctx, result)
        return result

    def record_human_decision(
        self, post: Post, approved: bool, label: Optional["object"] = None, reason: str = ""
    ) -> Result:
        """人工裁决写回闭环（FR-13 / AC-11）：通过→放行/正常，拒绝→拦截。

        写回缓存后，再遇"同图同文"会在缓存层复用此人工结论。
        """
        from .types import Decision, Label, StageName

        if approved:
            final_label, decision = Label.NORMAL, Decision.ALLOW
            reason = reason or "人工复核：通过（放行）。"
        else:
            final_label = label if isinstance(label, Label) else Label.FRAUD
            decision = Decision.BLOCK
            reason = reason or "人工复核：拒绝（拦截）。"

        result = Result(
            label=final_label, score=1.0, reason=reason,
            decision=decision, stage=StageName.HUMAN, post_id=post.post_id,
        )
        self.cache.write_verdict(post, result)
        return result

    def _maybe_cache(self, ctx: PipelineContext, result: Result) -> None:
        """高置信结论写回缓存（FR-4）：非缓存来源、且为自动放行/拦截时缓存。"""
        if result.stage == StageName.CACHE:
            return
        if result.decision in (Decision.ALLOW, Decision.BLOCK) and result.score >= 0.90:
            self.cache.store(ctx, result)
