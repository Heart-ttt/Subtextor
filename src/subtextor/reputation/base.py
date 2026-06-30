"""URL 信誉后端接口（FR-12）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class Verdict:
    """信誉查询结论。

    known_malicious: 是否命中已知恶意（True 才允许硬拦，HC-2）。
    source:          判定来源（用于可解释 reason，如 "local_list" / "safe_browsing"）。
    matched:         命中的 URL / 域名，便于展示。
    """

    known_malicious: bool = False
    source: str = ""
    matched: List[str] = field(default_factory=list)


class ReputationBackend(ABC):
    name: str = "reputation"

    @abstractmethod
    def check(self, urls: List[str]) -> Verdict:
        """查询一组 URL 的信誉。空列表应返回 known_malicious=False。"""
        raise NotImplementedError
