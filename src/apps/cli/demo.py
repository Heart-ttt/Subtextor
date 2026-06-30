"""最小可跑 demo（NFR-1 / AC-1）：对一个 Post 跑完整四级流水线，打印各级结果与理由。

用法：
  # 用内置合成对照样本（无需任何外部模型，建议先用 mock 后端离线跑通）：
  python -m subtextor.demo --backend mock --synth

  # 指定自己的图与配文：
  python -m subtextor.demo --image path/to/qr.png --text "扫码进群，兼职日结日入数百"

  # 用本地 llama.cpp（需先启动 server，见 README）：
  python -m subtextor.demo --image path/to/qr.png --text "..." --backend llamacpp
"""

from __future__ import annotations

import argparse
import json

from subtextor.config import load_config
from subtextor.pipeline import Pipeline
from subtextor.types import Post


def _print_result(title: str, post: Post, result) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'-' * 60}")
    print(f"配文: {post.text!r}")
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Subtextor 四级级联流水线 demo")
    ap.add_argument("--image", help="图片路径")
    ap.add_argument("--text", default="", help="配文")
    ap.add_argument("--backend", help="覆盖 VLM 后端：mock | llamacpp | remote")
    ap.add_argument("--prompt", help="覆盖 prompt 变体：base | strict | lenient | focus_fraud | focus_abuse")
    ap.add_argument("--synth", action="store_true", help="使用内置合成对照样本（AC-2 立意验证）")
    args = ap.parse_args()

    overrides = {}
    if args.backend:
        overrides["vlm"] = {"backend": args.backend}
    cfg = load_config(overrides=overrides)
    pipeline = Pipeline(cfg)

    if args.synth:
        # 生成一组"同图、不同配文"的对照样本，演示立意（AC-2）。
        from subtextor.synth.generate import build_contrast_pair

        pairs = build_contrast_pair()
        for title, post in pairs:
            result = pipeline.detect(post, prompt_variant=args.prompt)
            _print_result(title, post, result)
    else:
        if not args.image:
            ap.error("需要 --image，或使用 --synth 跑内置合成样本")
        post = Post(image=args.image, text=args.text, post_id="demo")
        result = pipeline.detect(post, prompt_variant=args.prompt)
        _print_result("单帖检测", post, result)

    print(f"\n{'=' * 60}\n运行统计（NFR-2）:")
    print(json.dumps(pipeline.stats.summary(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
