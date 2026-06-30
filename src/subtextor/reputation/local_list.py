"""本地名单信誉后端（默认）。

离线、零外网依赖：把 URL 的域名/子串与一份本地黑名单比对，命中即"已知恶意"。
名单来自 config.reputation.blocklist（可空），并内置几个**示意用**的假恶意域名，
仅供 demo 演示"通道一硬拦"路径——真实信誉服务（Safe Browsing 等）列 Future Work。

诚实边界（DESIGN 硬伤②）：本地名单只抓"已知"恶意目的地；导流诈骗常用干净/零信誉
链接，这里会返回 known_malicious=False，必须交由通道二（VLM）。
"""

from __future__ import annotations

from typing import List, Optional
from urllib.parse import urlparse

from .base import ReputationBackend, Verdict

# 示意用的假恶意域名（demo 演示硬拦路径；非真实数据）。
DEMO_BLOCKLIST = ["malware-demo.test", "phishing-example.test", "evil.test"]


def _host(url: str) -> str:
    try:
        netloc = urlparse(url if "://" in url else f"http://{url}").netloc.lower()
        return netloc.split("@")[-1].split(":")[0]
    except Exception:
        return url.lower()


class LocalListReputation(ReputationBackend):
    name = "local_list"

    def __init__(self, blocklist: Optional[List[str]] = None):
        # 用户名单 + 内置示意名单；统一小写。
        self.blocklist = [b.lower() for b in (blocklist or [])] + DEMO_BLOCKLIST

    def check(self, urls: List[str]) -> Verdict:
        matched = []
        for url in urls or []:
            host = _host(url)
            for bad in self.blocklist:
                if bad in host or bad in url.lower():
                    matched.append(url)
                    break
        return Verdict(known_malicious=bool(matched), source="local_list", matched=matched)
