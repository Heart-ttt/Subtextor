"""按配置构建 VLM 后端（FR-5 / HC-5）。

backend: llamacpp | remote | mock
  - llamacpp / remote 都走 OpenAI 兼容实现，仅 base_url/api_key/model 不同。
  - mock 用于离线跑通。
"""

from __future__ import annotations

from .base import VLMBackend


def build_vlm_backend(cfg: dict) -> VLMBackend:
    backend = cfg.get("vlm", {}).get("backend", "llamacpp")

    if backend == "mock":
        from .mock import MockVLM

        return MockVLM(cfg)

    # llamacpp / remote / 任意 OpenAI 兼容端点。
    from .openai_compatible import OpenAICompatibleVLM

    return OpenAICompatibleVLM(cfg)
