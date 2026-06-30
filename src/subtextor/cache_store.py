"""已判缓存层的持久化存储（FR-1）。

缓存键 = 图像感知哈希（pHash/dHash，近似命中）+ 配文指纹（精确匹配）。

为什么必须带配文（立意/AC-2 约束，HC-2）：违规是"图+文+语境"的联合属性。
若只按图像哈希缓存，"同一张二维码 + 诈骗话术"会污染"同一张二维码 + 正常点单"，
把两个应相反判定的帖子坍缩成一个——直接违背 AC-2。所以只有"同图且同文"的
真正重复帖才允许命中缓存（这恰是 FR-1 省成本的本意：避免对相同内容重复计算）。

图像侧用汉明距离阈值容忍压缩/缩放/水印等轻微改动；文本侧做规范化后精确比对。
后端用标准库 sqlite3，零额外依赖。命中返回历史结论，stage 标记为「缓存」。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Optional

from .types import Decision, Label, Result, StageName


def _hamming(a: str, b: str) -> int:
    """两个等长十六进制哈希字符串之间的汉明距离（按 bit 计）。"""
    if len(a) != len(b):
        return max(len(a), len(b)) * 4  # 长度不一致视为很远
    x = int(a, 16) ^ int(b, 16)
    return bin(x).count("1")


def normalize_text(text: str) -> str:
    """配文规范化指纹：去首尾空白、合并内部空白、小写。空配文归一化为 ""。"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip()).lower()


class VerdictCache:
    """基于"图像感知哈希 + 配文指纹"的判定缓存（FR-1）。"""

    def __init__(self, store_path: str, hamming_threshold: int = 5):
        self.path = Path(store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.threshold = hamming_threshold
        self._conn = sqlite3.connect(str(self.path))
        # 表名带 _v2：缓存键从"仅图像"升级为"图像+配文"，与旧 schema 不兼容。
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verdicts_v2 (
                phash    TEXT NOT NULL,
                text_key TEXT NOT NULL,
                label    TEXT NOT NULL,
                score    REAL NOT NULL,
                reason   TEXT NOT NULL,
                decision TEXT NOT NULL,
                post_id  TEXT,
                PRIMARY KEY (phash, text_key)
            )
            """
        )
        self._conn.commit()

    def lookup(self, phash: str, text: str) -> Optional[Result]:
        """命中条件：配文指纹相等 且 图像汉明距离 ≤ 阈值；返回最近一条，否则 None。"""
        tkey = normalize_text(text)
        rows = self._conn.execute(
            "SELECT phash, label, score, reason, decision, post_id "
            "FROM verdicts_v2 WHERE text_key = ?",
            (tkey,),
        ).fetchall()
        best = None
        best_dist = self.threshold + 1
        for ph, label, score, reason, decision, post_id in rows:
            d = _hamming(phash, ph)
            if d <= self.threshold and d < best_dist:
                best_dist = d
                best = (label, score, reason, decision, post_id, d)
        if best is None:
            return None
        label, score, reason, decision, post_id, dist = best
        return Result(
            label=Label(label),
            score=float(score),
            reason=f"{reason}（缓存命中：同图同文，图像汉明距离={dist}）",
            decision=Decision(decision),
            stage=StageName.CACHE,
            post_id=post_id,
            extra={"cache_hamming": dist},
        )

    def put(self, phash: str, text: str, result: Result) -> None:
        """写入/更新一条判定结论（键 = 图像哈希 + 配文指纹）。"""
        self._conn.execute(
            "INSERT OR REPLACE INTO verdicts_v2 VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                phash,
                normalize_text(text),
                result.label.value,
                float(result.score),
                result.reason,
                result.decision.value,
                result.post_id,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
