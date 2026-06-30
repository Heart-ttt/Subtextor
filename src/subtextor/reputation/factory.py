"""按配置构建信誉后端（FR-12 / HC-5 精神）。

config.reputation.backend: local_list（默认）| mock | （未来）safe_browsing
config.reputation.blocklist: 本地名单（域名/子串列表）
"""

from __future__ import annotations

from .base import ReputationBackend


def build_reputation(cfg: dict) -> ReputationBackend:
    rc = cfg.get("reputation", {})
    backend = rc.get("backend", "local_list")
    if backend == "mock":
        from .mock import MockReputation

        return MockReputation()
    # 默认本地名单。
    from .local_list import LocalListReputation

    return LocalListReputation(blocklist=rc.get("blocklist", []))
