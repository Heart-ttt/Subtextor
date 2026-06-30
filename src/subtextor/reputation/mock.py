"""Mock 信誉后端：对一切 URL 返回"未知/安全"。

用于演示"通道一不触发、必须走通道二"的常见形态（导流诈骗用干净链接）。
"""

from __future__ import annotations

from typing import List

from .base import ReputationBackend, Verdict


class MockReputation(ReputationBackend):
    name = "mock"

    def check(self, urls: List[str]) -> Verdict:
        return Verdict(known_malicious=False, source="mock(unknown)")
