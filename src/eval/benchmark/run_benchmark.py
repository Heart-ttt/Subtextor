"""benchmark：量化级联收益与图文联合增益（AC-5 / AC-6 / NFR-2）。

铁律：所有数字以实测为准，本脚本只负责跑出数字，绝不编造（交付物§）。
建议先用 mock 后端跑通流程，再切真实 VLM 复测。

输出两块：
  AC-5 成本量化：级联（仅 N% 进 VLM）vs 全量跑 VLM 的"进入 VLM 占比 + 端到端平均延迟"。
  AC-6 图文联合增量：在图文组合违规子集上，图文联合 VLM 相对 纯图像 / 纯文本 的召回。

用法：
  python -m benchmark.run_benchmark --backend mock --n 10
"""

from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

from subtextor.config import load_config
from subtextor.pipeline import Pipeline
from subtextor.textfilter import KeywordTextFilter
from subtextor.detectors import build_detector
from subtextor.types import Label, Post

from subtextor.paths import REPO_ROOT as ROOT


def _load_manifest(n_each: int):
    manifest_path = ROOT / "data" / "synth" / "manifest.json"
    if not manifest_path.exists():
        from subtextor.synth.generate import generate_dataset

        generate_dataset(n_each=n_each)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _posts(manifest):
    for s in manifest["samples"]:
        yield s, Post(image=str(ROOT / s["image"]), text=s["text"], post_id=s["image"])


def bench_cost(cfg, manifest):
    """AC-5：级联 vs 全量 VLM。"""
    cascade = Pipeline(cfg)
    t0 = time.perf_counter()
    for _, post in _posts(manifest):
        cascade.detect(post)
    cascade_wall = time.perf_counter() - t0

    full_cfg = copy.deepcopy(cfg)
    full_cfg["pipeline"]["stages"] = ["vlm"]  # 强制每帖都跑 VLM
    full = Pipeline(full_cfg)
    t0 = time.perf_counter()
    for _, post in _posts(manifest):
        full.detect(post)
    full_wall = time.perf_counter() - t0

    return {
        "cascade": cascade.stats.summary(),
        "cascade_wall_s": round(cascade_wall, 3),
        "full_vlm": full.stats.summary(),
        "full_vlm_wall_s": round(full_wall, 3),
        "speedup_x": round(full_wall / cascade_wall, 2) if cascade_wall else None,
    }


def _blank_image_path():
    """一张空白图：喂给 VLM 当"看不到图"的纯文本 LLM baseline 用。"""
    import tempfile

    from PIL import Image

    p = Path(tempfile.gettempdir()) / "subtextor_blank.png"
    if not p.exists():
        Image.new("RGB", (64, 64), (255, 255, 255)).save(p)
    return str(p)


def bench_joint_gain(cfg, manifest):
    """AC-6（修订）：违规子集上四方召回对比，核心是 图文联合 vs 纯文本 LLM 的增益。

    - 图文联合 VLM：完整流水线（图+文）。
    - 纯文本 LLM baseline：同一 VLM、但喂空白图（看不到图，只能靠文字）——硬伤①的对照。
    - 纯文本关键词：零成本词表 baseline。
    - 纯图像：视觉一刀切（检测到信号即判违规），用来反证一刀切会误伤。
    多模态增益 = 图文联合 − 纯文本 LLM；预期在"图像即道具"(img_prop) 子集上更显著。
    """
    from subtextor.prompts import get_prompt
    from subtextor.vlm import build_vlm_backend

    pipeline = Pipeline(cfg)
    text_kw = KeywordTextFilter()
    detector = build_detector(cfg)
    vlm = build_vlm_backend(cfg)
    blank = _blank_image_path()
    prompt = get_prompt(cfg.get("vlm", {}).get("prompt", "base"))

    violations = [(s, p) for s, p in _posts(manifest) if s["label"] != Label.NORMAL.value]
    total = len(violations)
    prop_total = sum(1 for s, _ in violations if s.get("img_prop"))
    hits = {"joint": 0, "text_llm": 0, "text_kw": 0, "image": 0}
    prop_hits = {"joint": 0, "text_llm": 0}

    for s, post in violations:
        # 图文联合
        joint_hit = pipeline.detect(post).label != Label.NORMAL
        # 纯文本 LLM：同模型、空白图
        tl = vlm.analyze(blank, post.text or "（无配文）", prompt)
        text_llm_hit = (not tl.degraded) and tl.label != Label.NORMAL
        if joint_hit:
            hits["joint"] += 1
        if text_llm_hit:
            hits["text_llm"] += 1
        if text_kw.screen(post.text).suspicion > 0:
            hits["text_kw"] += 1
        if detector.detect(post.image):
            hits["image"] += 1
        if s.get("img_prop"):
            prop_hits["joint"] += joint_hit
            prop_hits["text_llm"] += text_llm_hit

    def rc(h, t):
        return round(h / t, 4) if t else None

    return {
        "violation_samples": total,
        "recall_joint_image_text": rc(hits["joint"], total),
        "recall_text_only_llm": rc(hits["text_llm"], total),
        "recall_text_only_keyword": rc(hits["text_kw"], total),
        "recall_image_only": rc(hits["image"], total),
        "multimodal_gain_overall": rc(hits["joint"] - hits["text_llm"], total),
        "img_prop_subset": {
            "samples": prop_total,
            "recall_joint": rc(prop_hits["joint"], prop_total),
            "recall_text_only_llm": rc(prop_hits["text_llm"], prop_total),
            "multimodal_gain": rc(prop_hits["joint"] - prop_hits["text_llm"], prop_total),
        },
        "note": "多模态增益=图文联合−纯文本LLM；mock 后端忽略图像，故 mock 下增益≈0，需真实 VLM 复测。",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", help="覆盖 VLM 后端：mock | llamacpp | remote")
    ap.add_argument("--n", type=int, default=10, help="每类合成样本数")
    args = ap.parse_args()

    overrides = {}
    if args.backend:
        overrides["vlm"] = {"backend": args.backend}
    cfg = load_config(overrides=overrides)
    manifest = _load_manifest(args.n)

    print("== AC-5 成本量化 ==")
    print(json.dumps(bench_cost(cfg, manifest), ensure_ascii=False, indent=2))
    print("\n== AC-6 图文联合增量 ==")
    print(json.dumps(bench_joint_gain(cfg, manifest), ensure_ascii=False, indent=2))
    print("\n（数字以本次实测为准。切换 --backend 复测真实 VLM。）")


if __name__ == "__main__":
    main()
