"""VLM 后端子包（FR-5 / HC-5 / HC-6）。

统一接口 analyze(image, text, prompt) -> VLMResult；底层走 OpenAI 兼容协议，
本地 llama.cpp / 远程 API 仅靠改配置切换，不动流水线主逻辑。
"""

from .base import VLMBackend
from .factory import build_vlm_backend

__all__ = ["VLMBackend", "build_vlm_backend"]
