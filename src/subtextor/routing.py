"""severity → (score, decision) 的固定映射（DESIGN.md §4.4 / FR-4 / HC-7）。

铁律（HC-7）：VLM 层的 score 必须由本规则产生，不得直接采信模型自报的数值置信度。
本规则只用于 VLM 层；CNN/检测器层有自带真实 confidence，不走这里（§4.4）。
"""

from __future__ import annotations

from typing import Optional, Tuple

from .types import Decision, Label, Severity

# §4.4 的默认映射；实际值以 config.severity_map 为准（FR-8）。
DEFAULT_SEVERITY_SCORE = {
    Severity.CLEAR.value: 0.95,
    Severity.LIKELY.value: 0.70,
    Severity.UNSURE.value: 0.40,
}


def severity_to_score(severity: Optional[Severity], cfg: dict) -> float:
    """把 severity 映射为 score。降级态(None) 给最低分。"""
    if severity is None:
        return cfg.get("severity_map", {}).get(Severity.UNSURE.value, 0.40)
    smap = cfg.get("severity_map", DEFAULT_SEVERITY_SCORE)
    return float(smap.get(severity.value, DEFAULT_SEVERITY_SCORE[Severity.UNSURE.value]))


def map_vlm_decision(
    label: Label,
    severity: Optional[Severity],
    cfg: dict,
) -> Tuple[float, Decision]:
    """§4.4 分流：返回 (score, decision)。

    - severity=None（解析失败降级，§4.3 L3）→ 待人工（HC-6）。
    - clear：违规→拦截，正常→放行。
    - likely：违规且 score≥block_threshold→拦截，否则→待人工；正常→待人工（不够自信不自动放行）。
    - unsure：一律待人工。
    """
    block_threshold = float(cfg.get("routing", {}).get("block_threshold", 0.70))
    score = severity_to_score(severity, cfg)
    is_violation = label != Label.NORMAL

    if severity is None:
        return score, Decision.REVIEW

    if severity == Severity.CLEAR:
        return score, (Decision.BLOCK if is_violation else Decision.ALLOW)

    if severity == Severity.LIKELY:
        if is_violation:
            return score, (Decision.BLOCK if score >= block_threshold else Decision.REVIEW)
        return score, Decision.REVIEW

    # Severity.UNSURE
    return score, Decision.REVIEW
