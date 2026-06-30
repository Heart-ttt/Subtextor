"""② 轻量初筛层（FR-2，v2）。

逐帖都跑、要快。做四件事 + 两类硬拦：
  · L0 视觉：NSFW(ONNX) 打分 → 高分**硬拦**（确定性视觉证据，FR-14）。
  · 二维码：解码器检测并**解码 URL**（中性信号，喂通道一 + 喂 VLM）。
  · 图内字：OCR 抽取，并入文本（支付截图诈骗靠这一步路由到 VLM）。
  · 文侧：关键词粗筛 + 抽取文中 URL。
  · 通道一：把（解码 URL + 文中 URL）查信誉库 → 命中已知恶意**硬拦**（FR-11）。

定罪权限（HC-2）：
  · 确定性证据（NSFW 高分 / URL 命中恶意库）→ 允许硬拦。
  · 中性信号（二维码、软词、未知 URL）→ 只升级 VLM，绝不在此定罪。
出口：无任何信号 → 放行；有中性软信号 → 升级 VLM（返回 None）。
"""

from __future__ import annotations

from typing import List, Optional

from ..detectors import build_nsfw_detector, build_qr_detector
from ..ocr import build_ocr
from ..reputation import build_reputation
from ..textfilter import build_text_filter, extract_urls
from ..types import Decision, Label, Result, StageName
from .base import PipelineContext, Stage


class PrefilterStage(Stage):
    name = "prefilter"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.qr = build_qr_detector(cfg)
        self.nsfw = build_nsfw_detector(cfg)            # 可能为 None（关闭/缺模型）
        self.ocr = build_ocr(cfg)
        self.text_filter = build_text_filter(cfg)
        self.reputation = build_reputation(cfg)
        self.normal_score = cfg.get("prefilter", {}).get("normal_pass_score", 0.80)
        self.nsfw_threshold = cfg.get("nsfw", {}).get("block_threshold", 0.85)

    def process(self, ctx: PipelineContext) -> Optional[Result]:
        post = ctx.post

        # ── L0 视觉硬拦（确定性证据）──
        if self.nsfw is not None:
            for sig in self.nsfw.detect(post.image):
                if sig.type == "nsfw" and sig.confidence >= self.nsfw_threshold:
                    ctx.notes.append(f"L0：NSFW={sig.confidence:.2f} ≥ {self.nsfw_threshold} → 硬拦")
                    return self._block(
                        ctx, Label.NSFW, sig.confidence,
                        f"L0 视觉检测：NSFW 概率 {sig.confidence:.2f}，纯视觉违规直接硬拦。",
                    )

        # ── 二维码解码（中性信号）──
        ctx.signals = self.qr.detect(post.image)
        qr_urls = [s.meta["url"] for s in ctx.signals if s.meta.get("url")]

        # ── OCR + 合并文本 ──
        ctx.ocr_text = self.ocr.extract(post.image)
        combined = "\n".join(t for t in (post.text, ctx.ocr_text) if t)

        # ── 文中 URL + 通道一信誉硬拦 ──
        all_urls = qr_urls + extract_urls(combined)
        if all_urls:
            verdict = self.reputation.check(all_urls)
            if verdict.known_malicious:
                ctx.notes.append(f"通道一：命中已知恶意 {verdict.matched}（{verdict.source}）→ 硬拦")
                return self._block(
                    ctx, Label.FRAUD, 0.98,
                    f"通道一信誉：URL {verdict.matched} 命中已知恶意库（{verdict.source}），硬拦。",
                )

        # ── 文侧粗筛 ──
        tf = self.text_filter.screen(combined)
        ctx.text_suspicion = tf.suspicion

        has_visual = len(ctx.signals) > 0
        has_text = tf.suspicion > 0.0
        has_unknown_url = len(all_urls) > 0

        if not (has_visual or has_text or has_unknown_url):
            ctx.notes.append("初筛：无任何可疑信号 → 放行")
            return Result(
                label=Label.NORMAL, score=self.normal_score,
                reason="初筛：无可疑视觉信号、配文无风险软信号、无可疑链接，判定正常。",
                decision=Decision.ALLOW, stage=StageName.PREFILTER,
                post_id=post.post_id, signals=ctx.signals, ocr_text=ctx.ocr_text,
            )

        sig_types = sorted({s.type for s in ctx.signals})
        ctx.notes.append(
            f"初筛：视觉={sig_types or '无'} 文本怀疑={tf.suspicion:.2f} 未知URL={len(all_urls)} → 升级 VLM"
        )
        return None  # 中性信号，升级 VLM

    def _block(self, ctx, label, score, reason) -> Result:
        return Result(
            label=label, score=float(score), reason=reason,
            decision=Decision.BLOCK, stage=StageName.PREFILTER,
            post_id=ctx.post.post_id, signals=ctx.signals, ocr_text=ctx.ocr_text,
        )
