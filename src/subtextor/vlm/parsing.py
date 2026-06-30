"""VLM 结构化输出的容错解析（DESIGN.md §4.3 L2 / L3 校验部分）。

L2 · 容错解析：不直接 json.loads，先用正则抠出 {...} JSON 块（容忍"好的，结果如下："
或 ```json 包裹等杂质），再解析。对 Thinking 类模型，先剥离 <think>…</think> 推理段，
并以"最后一个 JSON 块"兜底，避免推理文字里的花括号干扰。
L3 · 校验：label / severity 必须落在允许枚举内，否则视为失败（交由 base 决定重试/降级）。
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from ..types import ALLOWED_LABELS, ALLOWED_SEVERITIES, Label, Severity, VLMResult

# 贪婪匹配第一个 { 到最后一个 } 的整段（容忍多数包裹杂质）。
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
# Thinking 模型的推理段：<think>…</think>（大小写不敏感），解析前剥离。
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _json_candidates(text: str) -> List[str]:
    """给出待解析的候选 JSON 串：贪婪整段 + "最后一个 {…}"兜底。"""
    candidates: List[str] = []
    m = _JSON_RE.search(text)
    if m:
        candidates.append(m.group(0))
    # 兜底：最后一个 { 到其后最后一个 }（Thinking 模型的最终答案通常在结尾）。
    li, ri = text.rfind("{"), text.rfind("}")
    if li != -1 and ri > li:
        tail = text[li : ri + 1]
        if tail not in candidates:
            candidates.append(tail)
    return candidates


def parse_vlm_json(raw: str) -> Optional[VLMResult]:
    """从 VLM 原始回复中解析出 VLMResult；失败或校验不过返回 None。"""
    if not raw:
        return None

    text = _THINK_RE.sub("", raw)  # 先剥离推理段（Thinking 模型）

    data = None
    for candidate in _json_candidates(text):
        for variant in (candidate, _strip_trailing_commas(candidate)):
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "label" in parsed:
                data = parsed
                break
        if data is not None:
            break
    if not isinstance(data, dict):
        return None

    label = str(data.get("label", "")).strip()
    severity = str(data.get("severity", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()

    # L3 校验：枚举不合法即判失败。
    if label not in ALLOWED_LABELS or severity not in ALLOWED_SEVERITIES:
        return None
    if not reason:
        reason = "（模型未给出理由）"

    return VLMResult(
        label=Label(label),
        severity=Severity(severity),
        reason=reason,
        degraded=False,
        raw=raw,
    )


def _strip_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)
