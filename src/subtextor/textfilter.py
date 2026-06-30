"""文侧轻量粗筛（FR-2）。

关键定位（HC-2）：粗筛只"提升不确定性、决定是否送 VLM"，绝不单独定罪。
默认实现是零依赖的关键词/正则粗筛器，抽象成可替换接口（未来可换小分类模型）。

输出一个 suspicion 分（0~1）和命中的软信号词，供初筛层决定是否升级到 VLM。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


# 文中 URL 抽取（喂通道一信誉查询，FR-11）。容忍 http(s):// 与裸域名两种形态。
_URL_RE = re.compile(
    r"(https?://[^\s，。、）)】]+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s，。、）)】]*)?)",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list:
    """从文本里抽取 URL / 裸域名，去重保序。"""
    if not text:
        return []
    seen, out = set(), []
    for m in _URL_RE.findall(text):
        u = m.strip().rstrip(".,)，。、")
        if u and "." in u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


@dataclass
class TextFilterResult:
    suspicion: float            # 0~1，越高越值得送 VLM
    matched: List[str] = field(default_factory=list)
    hint: str = ""              # 简短的人类可读说明（写进前置层 reason）


class TextFilter(ABC):
    name = "textfilter"

    @abstractmethod
    def screen(self, text: str) -> TextFilterResult:
        raise NotImplementedError


# 软信号词库：命中只提升怀疑度、决定"是否升级 VLM"，绝不等于违规（语境可能完全正常）。
# 含两类：① 话术类（配文里出现）；② 道具类（图像即道具场景，多来自 OCR 抽出的图内文字，
# 如支付截图的"支付成功"、海报的"扫码领取"）——确保支付截图/海报诈骗能被路由到 VLM。
FRAUD_HINTS = [
    # 话术类
    "日结", "日入", "兼职", "扫码进群", "扫码", "加微信", "加我",
    "名额有限", "内部渠道", "手机操作", "宝妈", "学生党", "轻松赚", "躺赚", "返利",
    "代理", "进群", "私聊", "vx", "薇信", "威信",
    # 道具类（支付截图 / 海报，常由 OCR 抽到）
    "支付成功", "已付款", "已经付", "转账成功", "发货", "收货",
    "扫码领取", "官方福利", "官方活动", "领取", "中奖", "补贴",
]
ABUSE_HINTS = [
    "废物", "垃圾", "去死", "滚", "脑残", "活该", "丑八怪", "贱",
]


class KeywordTextFilter(TextFilter):
    """关键词/正则粗筛器（默认）。"""

    name = "keyword"

    def __init__(self, fraud_hints=None, abuse_hints=None):
        self.fraud_hints = fraud_hints or FRAUD_HINTS
        self.abuse_hints = abuse_hints or ABUSE_HINTS

    def screen(self, text: str) -> TextFilterResult:
        if not text:
            return TextFilterResult(suspicion=0.0, hint="配文为空")

        low = text.lower()
        matched = [w for w in (self.fraud_hints + self.abuse_hints) if w.lower() in low]

        # 也粗筛 URL / 联系方式样式（软信号）。
        if re.search(r"(https?://|www\.|\d{6,}|[a-z]{2,}\d{3,})", low):
            matched.append("contact_or_url")

        if not matched:
            return TextFilterResult(suspicion=0.0, hint="配文未命中风险软信号")

        # 命中越多怀疑度越高，但封顶在 0.6：粗筛不给"高置信违规"，留给 VLM 定夺。
        suspicion = min(0.6, 0.25 + 0.1 * len(set(matched)))
        return TextFilterResult(
            suspicion=suspicion,
            matched=sorted(set(matched)),
            hint=f"配文命中软信号 {sorted(set(matched))}（仅提升不确定性，不定罪）",
        )


def build_text_filter(cfg: dict) -> TextFilter:
    """按 config.prefilter.text_filter 构建（目前仅 keyword）。"""
    # 预留扩展位：未来可接入小型文本分类模型。
    return KeywordTextFilter()
