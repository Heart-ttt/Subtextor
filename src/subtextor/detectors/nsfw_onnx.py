"""L0 视觉硬拦：NSFW 预训练模型 → ONNX 打分（FR-14 / AC-8）。

加载一个预训练 NSFW 分类模型的 ONNX，对图打"色情"分。高分由初筛层据 config 阈值
**硬拦**（纯视觉违规是"视觉决定"的，是合理的确定性证据，HC-2）。

★ 换模型只改这一个后处理文件 ★：输入尺寸、归一化、输出维度解释都在这里集中。
不同 NSFW 模型输出布局不一（有的输出 [sfw, nsfw] 两类，有的单 sigmoid），用
config.nsfw.nsfw_index / output_kind 适配。

合规（HC-1）：仓库不放 NSFW 图，只下模型权重；缺模型时返回空信号（不崩、不硬拦）。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from ..imaging import load_image
from ..types import Signal
from .base import Detector

# 多数 NSFW 模型（open_nsfw / nsfw_model 等）期望 224×224 + ImageNet 归一化。可被 config 覆盖。
DEFAULT_INPUT_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class NSFWDetector(Detector):
    name = "nsfw_onnx"

    def __init__(
        self,
        model_path: str,
        input_size: int = DEFAULT_INPUT_SIZE,
        nsfw_index: int = 1,
        nsfw_indices: Optional[List[int]] = None,  # 多个"违规类"概率求和（如 GantMan 的 hentai+porn）
        output_kind: str = "softmax2",  # softmax2 | sigmoid1 | probs（probs=模型末层已 softmax）
        normalize: bool = True,         # ImageNet 标准化（torchvision 系）；GantMan 只 /255 须关
        layout: str = "nchw",           # nchw（torch/onnx 系）| nhwc（TF/GantMan SavedModel→ONNX）
        rescale: bool = True,           # 是否 /255
    ):
        self.model_path = Path(model_path)
        self.input_size = input_size
        self.nsfw_index = nsfw_index
        self.nsfw_indices = nsfw_indices
        self.output_kind = output_kind
        self.normalize = normalize
        self.layout = layout
        self.rescale = rescale
        self._session = None
        self._missing = False

    def _ensure(self) -> bool:
        if self._missing:
            return False
        if self._session is not None:
            return True
        if not self.model_path.exists():
            self._missing = True
            return False
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
            return True
        except Exception as e:  # pragma: no cover
            print(f"[nsfw] 加载 ONNX 失败，跳过 L0：{e}")
            self._missing = True
            return False

    def _preprocess(self, image):
        import numpy as np

        img = load_image(image).convert("RGB").resize((self.input_size, self.input_size))
        arr = np.asarray(img, dtype="float32")
        if self.rescale:
            arr = arr / 255.0
        if self.normalize:  # ImageNet 标准化（torchvision 系）；GantMan 这类只 /255 的模型须关
            arr = (arr - np.array(IMAGENET_MEAN, "float32")) / np.array(IMAGENET_STD, "float32")
        if self.layout == "nchw":  # 否则保持 NHWC（TF/GantMan SavedModel→ONNX 的输入布局）
            arr = arr.transpose(2, 0, 1)
        return arr[None, ...].astype("float32")

    def _violation_indices(self) -> List[int]:
        return list(self.nsfw_indices) if self.nsfw_indices else [self.nsfw_index]

    def score(self, image: Union[str, bytes]) -> Optional[float]:
        """返回"违规"概率（0~1）；多类时为各违规类概率之和；模型缺失返回 None。"""
        import numpy as np

        if not self._ensure():
            return None
        x = self._preprocess(image)
        name = self._session.get_inputs()[0].name
        out = np.asarray(self._session.run(None, {name: x})[0]).reshape(-1)
        if self.output_kind == "sigmoid1":
            return float(1.0 / (1.0 + np.exp(-out[0])))
        if self.output_kind == "probs":
            probs = out  # 模型末层已 softmax（如 GantMan），直接当概率用，勿再 softmax
        else:  # softmax2 / softmaxN：对 logits 现算 softmax
            e = np.exp(out - out.max())
            probs = e / e.sum()
        idxs = [i for i in self._violation_indices() if 0 <= i < len(probs)] or [len(probs) - 1]
        return float(sum(probs[i] for i in idxs))

    def detect(self, image: Union[str, bytes]) -> List[Signal]:
        s = self.score(image)
        if s is None:
            return []
        return [Signal(type="nsfw", confidence=s)]
