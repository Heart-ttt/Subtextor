"""OpenAI 兼容协议的 VLM 后端（FR-5 / HC-5）。

同一实现覆盖本地 llama.cpp server、边缘小 VLM、远程云 API——
切换形态只改 config 的 base_url / api_key / model，不动这里、不动流水线主逻辑。
"""

from __future__ import annotations

from typing import Union

from ..imaging import to_data_uri
from .base import VLMBackend


class OpenAICompatibleVLM(VLMBackend):
    name = "openai_compatible"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        vcfg = cfg.get("vlm", {})
        self.base_url = vcfg.get("base_url", "http://127.0.0.1:8080/v1")
        self.api_key = vcfg.get("api_key", "sk-no-key-required")
        self.timeout = float(vcfg.get("timeout", 60))
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:  # pragma: no cover
                raise ImportError("OpenAI 兼容后端需要 openai 包，请先 `pip install openai`。") from e
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
        return self._client

    def _chat(self, image: Union[str, bytes], text: str, prompt_text: str, temperature: float) -> str:
        client = self._ensure_client()
        data_uri = to_data_uri(image)
        messages = [
            {"role": "system", "content": prompt_text},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"配文与图内文字如下：\n{text}"},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ]
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content or ""
