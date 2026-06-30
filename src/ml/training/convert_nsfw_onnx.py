"""L0 NSFW 模型 → ONNX 转换/获取（FR-14 / AC-8 的"部署"端）。

定位：边缘 AI 的核心技能是"拿一个真实预训练模型 → 转 ONNX → onnxruntime 部署"，
不一定要自训。本脚本把"获取一个 NSFW 预训练模型并产出 models/nsfw.onnx"封装起来。

合规（HC-1）：只下载/转换**模型权重**，不下载任何 NSFW 图像。

两种来源（按可得性二选一）：
  A. 已是 ONNX：直接从给定 URL 下载到 models/nsfw.onnx（最简）。
  B. Keras/TF 预训练（如 GantMan nsfw_model）：用 tf2onnx 转换。

注意：具体可用的权重地址会随社区变动，脚本默认走"本地已有文件则跳过、否则提示来源"，
不写死可能失效的 URL；首次使用请按下方说明填入你确认可用的来源。

用法：
  python -m training.convert_nsfw_onnx --from-onnx <url-or-path>      # 来源 A
  python -m training.convert_nsfw_onnx --from-keras <saved_model_dir> # 来源 B（需 tf2onnx）
  python -m training.convert_nsfw_onnx --check                        # 只检查 models/nsfw.onnx
"""

from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

from subtextor.paths import REPO_ROOT as ROOT

OUT = ROOT / "models" / "nsfw.onnx"

# 常见来源（社区可能变动，使用前请自行确认可用性）：
#   - GantMan/nsfw_model（Keras）：https://github.com/GantMan/nsfw_model
#   - yahoo/open_nsfw（Caffe，需转换）
#   - Hugging Face 上若有现成的 *nsfw*.onnx，可直接用 --from-onnx 指向其 resolve 链接。
SUGGESTED_SOURCES = (
    "GantMan/nsfw_model (Keras→tf2onnx) | yahoo open_nsfw | HF 上的 nsfw onnx"
)

# ── 已验证配方（GantMan nsfwjs MobileNetV2，2026-06）──────────────────────────
# 1) 下 SavedModel（避开 .h5 在新 Keras 下的加载坑 #99）：
#    releases/download/1.1.0/nsfw_mobilenet_v2_140_224.zip → 解出 mobilenet_v2_140_224/
# 2) 装 tensorflow + tf2onnx（须 numpy<2，与 paddle/opencv 一致），再：
#    python -m training.convert_nsfw_onnx --from-keras <解压目录>/mobilenet_v2_140_224
#    （内部 = tf2onnx.convert --saved-model ... --opset 13；用 tf.saved_model.load 绕开 Keras）
# 3) 产物：input[N,224,224,3](NHWC) → prediction[N,5]，末层已 softmax。
#    类序: 0=drawings 1=hentai 2=neutral 3=porn 4=sexy。预处理只 /255，不做 ImageNet 标准化。
#    对应 config.nsfw: layout=nhwc / normalize=false / output_kind=probs / nsfw_indices=[1,3]（拦 hentai+porn）。


def from_onnx(src: str) -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if src.startswith(("http://", "https://")):
        print(f"· 下载 ONNX：{src}")
        urllib.request.urlretrieve(src, OUT)
    else:
        shutil.copy(src, OUT)
    print(f"✓ 已就绪：{OUT}")
    return OUT


def from_keras(saved_model_dir: str) -> Path:
    print("· 用 tf2onnx 转换 Keras/SavedModel → ONNX（需 `pip install tf2onnx tensorflow`）")
    import subprocess

    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["python", "-m", "tf2onnx.convert", "--saved-model", saved_model_dir,
         "--output", str(OUT), "--opset", "13"],
        check=True,
    )
    print(f"✓ 已转换：{OUT}")
    return OUT


def main() -> None:
    ap = argparse.ArgumentParser(description="NSFW 预训练模型 → ONNX")
    ap.add_argument("--from-onnx", help="ONNX 文件的 URL 或本地路径")
    ap.add_argument("--from-keras", help="Keras SavedModel 目录")
    ap.add_argument("--check", action="store_true", help="只检查 models/nsfw.onnx 是否存在")
    args = ap.parse_args()

    if args.check:
        print("✓ 已存在" if OUT.exists() else "✗ 不存在（L0 将自动跳过，不影响其余链路）", OUT)
        return
    if args.from_onnx:
        from_onnx(args.from_onnx)
    elif args.from_keras:
        from_keras(args.from_keras)
    else:
        print("请用 --from-onnx <url|path> 或 --from-keras <dir>。")
        print(f"可选来源：{SUGGESTED_SOURCES}")
        print("提示：确认好可用权重后，把它转/放到", OUT)


if __name__ == "__main__":
    main()
