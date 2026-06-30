"""图像读取与感知哈希工具。

对外声明只支持 jpg/png，但用通用图像库读取（顺带兼容 webp/bmp 等，IB-3）；
遇不支持格式明确报错而非崩溃。
"""

from __future__ import annotations

import base64
import io
from typing import Union


def load_image(image: Union[str, bytes]):
    """把路径或二进制读成 PIL.Image（RGB）。失败时抛出清晰错误（IB-3）。"""
    try:
        from PIL import Image
    except ImportError as e:  # pragma: no cover
        raise ImportError("读取图像需要 Pillow，请先 `pip install pillow`。") from e

    try:
        if isinstance(image, bytes):
            img = Image.open(io.BytesIO(image))
        else:
            img = Image.open(image)
        return img.convert("RGB")
    except Exception as e:
        raise ValueError(f"无法读取图像（不支持的格式或文件损坏）：{e}") from e


def perceptual_hash(image: Union[str, bytes], algo: str = "phash") -> str:
    """计算感知哈希，返回十六进制字符串（FR-1）。algo: phash | dhash | ahash。"""
    try:
        import imagehash
    except ImportError as e:  # pragma: no cover
        raise ImportError("计算感知哈希需要 imagehash，请先 `pip install imagehash`。") from e

    img = load_image(image)
    fn = {
        "phash": imagehash.phash,
        "dhash": imagehash.dhash,
        "ahash": imagehash.average_hash,
    }.get(algo, imagehash.phash)
    return str(fn(img))


def to_data_uri(image: Union[str, bytes], fmt: str = "JPEG") -> str:
    """把图像编码为 OpenAI 兼容协议所需的 data URI（base64）。"""
    img = load_image(image)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = "image/jpeg" if fmt.upper() in ("JPEG", "JPG") else f"image/{fmt.lower()}"
    return f"data:{mime};base64,{b64}"
