"""核心数据结构与枚举（DESIGN.md §4 I/O Contract、§9 模块清单）。

刻意用标准库 dataclass + Enum，零额外依赖，便于在边缘/最小环境里也能 import。
对外的违规类别枚举固定为 诈骗导流 | 网络暴力 | 正常（§3）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union


class Label(str, Enum):
    """对外暴露的违规类别枚举（§3）。

    FRAUD/ABUSE/NORMAL 是 L1 语境层（VLM）的输出；NSFW 是 L0 纯视觉硬拦的输出（FR-14）。
    VLM 仍只允许返回前三类（见 VLM_LABELS），不得自创或输出 NSFW。
    """

    FRAUD = "诈骗导流"
    ABUSE = "网络暴力"
    NORMAL = "正常"
    NSFW = "色情"   # L0 纯视觉违规（仅由 NSFW 检测器硬拦产生，不由 VLM 输出）


class Decision(str, Enum):
    """三档分流决策（§4.2 / FR-4）。"""

    ALLOW = "放行"
    BLOCK = "拦截"
    REVIEW = "待人工"


class StageName(str, Enum):
    """结论在哪一级得出（§4.2 Result.stage）。"""

    CACHE = "缓存"
    PREFILTER = "初筛"
    VLM = "VLM"
    HUMAN = "人工"  # 人工裁决写回闭环（FR-13 / AC-11）


class Severity(str, Enum):
    """VLM 返回的粗粒度判断强度（§4.4），再由固定规则映射成 score 与决策。

    注意：取值用小写字符串，与 prompt 约定、config.severity_map 的键一一对应。
    """

    CLEAR = "clear"      # 明确（违规或正常）
    LIKELY = "likely"    # 较可能但不确定
    UNSURE = "unsure"    # 模棱两可


# VLM 结构化输出允许的 label（§4.3 L3 校验用）：只含 L1 三类，**不含 NSFW**，
# 防止 VLM 自创或越权输出纯视觉类别。NSFW 只能由 L0 检测器产生。
VLM_LABELS = {Label.FRAUD.value, Label.ABUSE.value, Label.NORMAL.value}
ALLOWED_LABELS = VLM_LABELS  # 向后兼容别名（parsing 用）
ALLOWED_SEVERITIES = {sev.value for sev in Severity}


@dataclass
class Post:
    """系统的基本处理单位（§4.1）。

    image: 单张图片，路径(str) 或 二进制(bytes)，必填（IB-1）。
    text:  配文，可为空字符串（容忍只发图，IB-1）。
    post_id: 可选，便于缓存与追溯。

    纯文字帖（无图）不在范围内（IB-2）；图内文字由初筛层 OCR 抽取，
    不是这里的输入字段（IB-4）。
    """

    image: Union[str, bytes]
    text: str = ""
    post_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.image is None or (isinstance(self.image, str) and not self.image.strip()):
            # 图片必填（IB-1）。明确报错而非崩溃在下游（IB-3 精神）。
            raise ValueError("Post.image 必填：图片是核心模态，纯文字帖不在本项目范围（IB-2）。")
        if self.text is None:
            self.text = ""


@dataclass
class Signal:
    """初筛层检测器输出的中性视觉信号（FR-9）。

    type:       信号类型，如 "qrcode" / "barcode" / "contact_region"
    bbox:       (x1, y1, x2, y2) 像素坐标，可为 None
    confidence: 检测器自带的真实置信度（§4.4：检测器层不走 severity 映射）
    """

    type: str
    confidence: float
    bbox: Optional[tuple] = None
    meta: dict = field(default_factory=dict)


@dataclass
class VLMResult:
    """VLM 精判层的结构化输出（§4.3 / FR-3）。

    severity 为 None 表示三层机制（§4.3）解析/校验失败后的降级态，
    下游须据此把决策降为「待人工」（HC-6）。
    """

    label: Label
    reason: str
    severity: Optional[Severity] = None
    degraded: bool = False
    raw: Optional[str] = None  # 保留原始回复，便于调试与审计


@dataclass
class Result:
    """每次检测的结构化结果（§4.2，必须至少包含以下字段）。"""

    label: Label
    score: float
    reason: str
    decision: Decision
    stage: StageName

    # 以下为可选的附加诊断信息，便于审核台展示与 benchmark 统计（不在最小契约内）。
    post_id: Optional[str] = None
    signals: list = field(default_factory=list)
    ocr_text: str = ""
    latency_ms: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转为可 JSON 序列化的精简字典（审核台 / API 用）。"""
        return {
            "label": self.label.value,
            "score": round(self.score, 4),
            "reason": self.reason,
            "decision": self.decision.value,
            "stage": self.stage.value,
            "post_id": self.post_id,
            "signals": [
                {"type": s.type, "confidence": round(s.confidence, 4), "bbox": s.bbox}
                for s in self.signals
            ],
            "ocr_text": self.ocr_text,
            "latency_ms": round(self.latency_ms, 2),
        }
