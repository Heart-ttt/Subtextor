"""通道一：URL 信誉后端（FR-11 / FR-12）。

统一接口 check(urls) -> Verdict；本地名单 / mock / 真实服务可插拔。
命中已知恶意目的地 → 允许在初筛硬拦（确定性证据，HC-2）。
"""

from .base import ReputationBackend, Verdict
from .factory import build_reputation

__all__ = ["ReputationBackend", "Verdict", "build_reputation"]
