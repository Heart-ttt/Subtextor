"""核心契约的最小测试：结构化稳健（AC-7）与 severity 映射（§4.4 / HC-7）。

可直接 `python -m tests.test_parsing_and_routing` 运行（无需 pytest）。
"""

from __future__ import annotations

from subtextor.routing import map_vlm_decision
from subtextor.types import Decision, Label, Severity
from subtextor.vlm.parsing import parse_vlm_json


def test_parse_clean_json():
    r = parse_vlm_json('{"label":"正常","severity":"clear","reason":"图文无风险"}')
    assert r is not None and r.label == Label.NORMAL and r.severity == Severity.CLEAR


def test_parse_with_junk_wrapper():
    # L2 容错：容忍前导文字与代码块包裹。
    raw = '好的，结果如下：\n```json\n{"label":"诈骗导流","severity":"likely","reason":"x"}\n```'
    r = parse_vlm_json(raw)
    assert r is not None and r.label == Label.FRAUD


def test_parse_thinking_model_output():
    # Thinking 模型：先 <think> 推理（含干扰花括号）再给最终 JSON，应正确抠出答案。
    raw = (
        "<think>用户图里有二维码 {可能是群码} 配文像兼职诈骗，我倾向诈骗导流</think>\n"
        '最终结果：{"label":"诈骗导流","severity":"clear","reason":"二维码+兼职诱导话术"}'
    )
    r = parse_vlm_json(raw)
    assert r is not None and r.label == Label.FRAUD and r.severity == Severity.CLEAR


def test_parse_illegal_label_returns_none():
    # AC-7：非法 label → 解析失败（交由 base 降级人工）。
    assert parse_vlm_json('{"label":"涉政","severity":"clear","reason":"x"}') is None
    assert parse_vlm_json("完全不是 JSON 的脏文本") is None


def test_severity_mapping():
    cfg = {"severity_map": {"clear": 0.95, "likely": 0.70, "unsure": 0.40},
           "routing": {"block_threshold": 0.70}}
    # clear 违规 → 拦截
    s, d = map_vlm_decision(Label.FRAUD, Severity.CLEAR, cfg)
    assert s == 0.95 and d == Decision.BLOCK
    # clear 正常 → 放行
    _, d = map_vlm_decision(Label.NORMAL, Severity.CLEAR, cfg)
    assert d == Decision.ALLOW
    # unsure → 待人工
    _, d = map_vlm_decision(Label.ABUSE, Severity.UNSURE, cfg)
    assert d == Decision.REVIEW
    # 降级（severity=None）→ 待人工（HC-6）
    _, d = map_vlm_decision(Label.NORMAL, None, cfg)
    assert d == Decision.REVIEW


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("全部通过。")


if __name__ == "__main__":
    _run_all()
