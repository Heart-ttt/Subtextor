"""VLM 三层结构化兜底的编排测试（§4.3 / HC-6 / AC-7）。

现有 test_parsing_and_routing 只测到 parse_vlm_json（L2 单元）与 map_vlm_decision（§4.4）。
本测试补的是 base.VLMBackend.analyze() 把三层串起来的**编排契约**：
脏输出 → 降温重试一次 → 仍失败则降级为 severity=None（待人工），调用抛异常也绝不崩。

用一个可控的假后端驱动，不联网、不需要图像/模型，纯标准库可跑：
  python -m tests.test_vlm_degradation
"""

from __future__ import annotations

import json

from subtextor.routing import map_vlm_decision
from subtextor.types import Decision, Label, Severity
from subtextor.vlm.base import VLMBackend

_CFG = {"vlm": {"temperature": 0.2, "retry_temperature": 0.0},
        "severity_map": {"clear": 0.95, "likely": 0.70, "unsure": 0.40},
        "routing": {"block_threshold": 0.70}}


class _ScriptedVLM(VLMBackend):
    """按预设脚本逐次返回回复；记录每次调用的温度，便于断言重试行为。"""

    name = "scripted"

    def __init__(self, replies, cfg=_CFG):
        super().__init__(cfg)
        self._replies = list(replies)
        self.calls = []  # 每次 _chat 的温度，长度即调用次数

    def _chat(self, image, text, prompt_text, temperature):
        self.calls.append(temperature)
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _json(label="正常", severity="clear", reason="x"):
    return json.dumps({"label": label, "severity": severity, "reason": reason}, ensure_ascii=False)


def test_clean_output_no_retry_no_degrade():
    """首次即合法 → 直接返回，不重试、不降级。"""
    vlm = _ScriptedVLM([_json("诈骗导流", "clear", "扫码导流")])
    r = vlm.analyze("img", "扫码进群", "base prompt")
    assert r.label == Label.FRAUD and r.severity == Severity.CLEAR
    assert r.degraded is False
    assert len(vlm.calls) == 1  # 没有触发重试


def test_garbage_then_valid_retries_once_at_retry_temp():
    """首次脏输出 → 降温重试一次 → 第二次合法则采用（L3 重试成功）。"""
    vlm = _ScriptedVLM(["完全不是 JSON 的脏文本", _json("正常", "clear", "无风险")])
    r = vlm.analyze("img", "今天天气不错", "base prompt")
    assert r.label == Label.NORMAL and r.severity == Severity.CLEAR and r.degraded is False
    assert vlm.calls == [0.2, 0.0]  # 第二次用 retry_temperature 降温


def test_garbage_twice_degrades_to_review():
    """两次都不可解析 → 降级 severity=None/degraded，且映射为待人工（HC-6 绝不漏脏数据）。"""
    vlm = _ScriptedVLM(["前言不搭后语", '{"label":"涉政","severity":"clear","reason":"非法枚举"}'])
    r = vlm.analyze("img", "x", "base prompt")
    assert r.degraded is True and r.severity is None and r.label == Label.NORMAL
    assert len(vlm.calls) == 2
    # 编排闭合到 §4.4：降级态必须落到「待人工」。
    _, decision = map_vlm_decision(r.label, r.severity, _CFG)
    assert decision == Decision.REVIEW


def test_first_call_exception_degrades_without_crash():
    """底层调用抛异常 → 捕获并降级待人工，绝不让异常冒泡崩流水线。"""
    vlm = _ScriptedVLM([RuntimeError("server 502")])
    r = vlm.analyze("img", "x", "base prompt")
    assert r.degraded is True and r.severity is None
    assert len(vlm.calls) == 1
    _, decision = map_vlm_decision(r.label, r.severity, _CFG)
    assert decision == Decision.REVIEW


def test_retry_call_exception_degrades_without_crash():
    """首次脏输出、重试时底层抛异常 → 仍降级待人工不崩。"""
    vlm = _ScriptedVLM(["脏文本", RuntimeError("超时")])
    r = vlm.analyze("img", "x", "base prompt")
    assert r.degraded is True and r.severity is None
    assert len(vlm.calls) == 2


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("全部通过。")


if __name__ == "__main__":
    _run_all()
