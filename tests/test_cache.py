"""缓存层回归测试：同图不同文不得串缓存（AC-2 / HC-2 命门）。

历史 bug：缓存只按图像 pHash 做 key，导致"同一张二维码 + 诈骗话术"的拦截结论
污染了"同一张二维码 + 正常点单"，把两个应相反判定的帖子坍缩成一个。
本测试固化修复：缓存键 = 图像哈希(近似) + 配文(精确)。

只用标准库 sqlite3，可直接 `python -m tests.test_cache` 运行。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from subtextor.cache_store import VerdictCache
from subtextor.types import Decision, Label, Result, StageName

# 两个等长的十六进制 pHash：PHASH_A 与 PHASH_NEAR 仅差 1 bit（近似），与 PHASH_FAR 很远。
PHASH_A = "ffffffffffffffff"
PHASH_NEAR = "fffffffffffffffe"   # 与 A 汉明距离 = 1
PHASH_FAR = "0000000000000000"    # 与 A 汉明距离 = 64

FRAUD_TEXT = "扫码进群 兼职日结 日入数百"
NORMAL_TEXT = "我们家小店的点单码，堂食扫这个就能下单"


def _block_result():
    return Result(
        label=Label.FRAUD, score=0.95, reason="诈骗导流",
        decision=Decision.BLOCK, stage=StageName.VLM, post_id="a",
    )


def _new_cache(threshold=5):
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    return VerdictCache(tmp.name, hamming_threshold=threshold)


def test_same_image_different_text_is_a_miss():
    """核心回归：同图 + 不同配文 → 不命中（必须放行到 VLM 重判）。"""
    c = _new_cache()
    c.put(PHASH_A, FRAUD_TEXT, _block_result())
    assert c.lookup(PHASH_A, FRAUD_TEXT) is not None      # 同图同文 → 命中
    assert c.lookup(PHASH_A, NORMAL_TEXT) is None          # 同图异文 → 必须 miss


def test_near_image_same_text_is_a_hit():
    """图像轻微改动 + 同配文 → 仍命中（保留缓存省成本本意）。"""
    c = _new_cache(threshold=5)
    c.put(PHASH_A, FRAUD_TEXT, _block_result())
    hit = c.lookup(PHASH_NEAR, FRAUD_TEXT)
    assert hit is not None and hit.decision == Decision.BLOCK


def test_far_image_same_text_is_a_miss():
    """图像差异超过阈值 → 不命中（即便配文相同）。"""
    c = _new_cache(threshold=5)
    c.put(PHASH_A, FRAUD_TEXT, _block_result())
    assert c.lookup(PHASH_FAR, FRAUD_TEXT) is None


def test_text_normalization():
    """配文规范化：空白差异不影响命中。"""
    c = _new_cache()
    c.put(PHASH_A, FRAUD_TEXT, _block_result())
    assert c.lookup(PHASH_A, f"  {FRAUD_TEXT}  ") is not None


def test_human_verdict_reused():
    """闭环（FR-13/AC-11）：人工裁决写回后，再遇同图同文复用其结论。"""
    c = _new_cache()
    human = Result(
        label=Label.NORMAL, score=1.0, reason="人工复核：通过",
        decision=Decision.ALLOW, stage=StageName.HUMAN, post_id="x",
    )
    c.put(PHASH_A, FRAUD_TEXT, human)
    hit = c.lookup(PHASH_A, FRAUD_TEXT)
    assert hit is not None and hit.label == Label.NORMAL and hit.decision == Decision.ALLOW


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("全部通过。")


if __name__ == "__main__":
    _run_all()
