"""Mock VLM 后端：离线把四级流水线与容错降级（§4.3/§4.4）跑通。

不联网、不需要 llama.cpp server。基于配文里的软信号做一个朴素的"假装图文联合"
判断，输出符合 §4.3 L1 格式的 JSON 字符串，再交给基类的三层机制解析。

它只为让最小 demo / 测试 / benchmark 在无模型时也能端到端运行；
真实判定质量请切到 OpenAI 兼容后端（本地 llama.cpp 或远程 API）。
"""

from __future__ import annotations

import json
from typing import Union

from ..textfilter import ABUSE_HINTS
from .base import VLMBackend

# mock 的"诈骗意图"词表：刻意只含话术级意图词，不含截图道具词（如"支付成功"）——
# 否则会把"支付截图+正常记账"也误判。这让 mock 能靠配文意图区分对照 A/B（同图不同文）。
# 注意：这只是离线 stub 的近似；真实判定需 VLM 看图，切 llamacpp/remote 后端。
MOCK_FRAUD_INTENT = [
    # 交易诈骗（催发货）
    "发货", "请发", "尽快发", "马上安排发", "先发",
    # 海报导流
    "扫码领取", "官方福利", "官方活动", "名额有限", "中奖", "领补贴", "领取补贴",
    # 二维码导流 / 兼职
    "日入", "日结", "兼职", "扫码进群", "加微信", "加我", "代理", "躺赚", "轻松赚",
    "私聊", "薇信", "威信", "vx", "进群", "宝妈", "学生党",
]


class MockVLM(VLMBackend):
    name = "mock"

    def _chat(self, image: Union[str, bytes], text: str, prompt_text: str, temperature: float) -> str:
        low = (text or "").lower()
        fraud_hits = [w for w in MOCK_FRAUD_INTENT if w.lower() in low]
        abuse_hits = [w for w in ABUSE_HINTS if w.lower() in low]

        # 故意模拟"图文联合"：这里把"配文软信号"当作组合证据的占位。
        if fraud_hits and abuse_hits:
            label, severity = ("诈骗导流", "likely")
            reason = "配文同时含导流与攻击性表述，结合图像综合判断偏诈骗导流（mock 占位推理）。"
        elif fraud_hits:
            label, severity = ("诈骗导流", "clear" if len(fraud_hits) >= 2 else "likely")
            reason = f"图中视觉元素配合配文中的诱导话术{fraud_hits}，构成扫码/导流风险（mock 占位推理）。"
        elif abuse_hits:
            label, severity = ("网络暴力", "clear" if len(abuse_hits) >= 2 else "likely")
            reason = f"配文含针对特定对象的侮辱性表述{abuse_hits}，结合人物图判定网络暴力（mock 占位推理）。"
        else:
            label, severity = ("正常", "clear")
            reason = "图文组合无导流/攻击语境，判定正常（mock 占位推理）。"

        # 故意混入杂质，顺便检验基类 L2 容错解析。
        payload = {"label": label, "severity": severity, "reason": reason}
        return f"好的，结果如下：\n```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
