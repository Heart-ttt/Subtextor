"""① 已判缓存层（感知哈希）—— FR-1。

命中已判记录（近似命中，容忍轻微改动）则直接返回历史结论，不进入后续环节。
"""

from __future__ import annotations

from typing import Optional

from ..cache_store import VerdictCache
from ..config import resolve_path
from ..imaging import perceptual_hash
from ..types import Result
from .base import PipelineContext, Stage


class CacheStage(Stage):
    name = "cache"

    def __init__(self, cfg: dict):
        ccfg = cfg.get("cache", {})
        self.enabled = ccfg.get("enabled", True)
        self.algo = ccfg.get("hash_algo", "phash")
        store_path = resolve_path(cfg, ccfg.get("store_path", ".cache/verdicts.sqlite"))
        self.cache = VerdictCache(
            str(store_path), hamming_threshold=ccfg.get("hamming_threshold", 5)
        )

    def process(self, ctx: PipelineContext) -> Optional[Result]:
        if not self.enabled:
            return None
        ctx.phash = perceptual_hash(ctx.post.image, self.algo)
        # 缓存键含配文：同图不同文不得命中（AC-2 / HC-2）。
        hit = self.cache.lookup(ctx.phash, ctx.post.text)
        if hit is not None:
            hit.post_id = ctx.post.post_id
            ctx.notes.append("缓存：命中历史结论，直接返回（零成本）")
            hit.extra.setdefault("trace", list(ctx.notes))
            return hit
        ctx.notes.append("缓存未命中")
        return None

    def store(self, ctx: PipelineContext, result: Result) -> None:
        """供流水线在得出高置信结论后写回缓存（FR-4）。"""
        if self.enabled and ctx.phash:
            self.cache.put(ctx.phash, ctx.post.text, result)

    def write_verdict(self, post, result: Result) -> None:
        """直接为某帖写回结论（无 ctx，用于人工裁决闭环 FR-13）。"""
        if self.enabled:
            phash = perceptual_hash(post.image, self.algo)
            self.cache.put(phash, post.text, result)
