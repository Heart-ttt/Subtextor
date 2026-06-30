"""Subtextor —— 图文语境违规检测流水线。

读图文"潜台词"的执行者；对外只暴露最常用的几个符号，细节见各子模块。
"""

from .types import (
    Post,
    Signal,
    VLMResult,
    Result,
    Label,
    Decision,
    StageName,
    Severity,
)

__all__ = [
    "Post",
    "Signal",
    "VLMResult",
    "Result",
    "Label",
    "Decision",
    "StageName",
    "Severity",
]

__version__ = "0.1.0"
