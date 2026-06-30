"""Prompt 作为一等资产（FR-7 / NFR-3）。

所有 VLM prompt 独立成 prompts/ 下的 .txt 文件，可版本管理、可运行时切换，
绝不硬编码散落在推理代码里。审核台据此提供"侧重点"下拉（FR-6）。

每个变体文件名即其 key（去掉 .txt）。文件内容须包含（§4.3 L1 / §4.4 / FR-7）：
  · 违规类别定义（固定枚举：诈骗导流 | 网络暴力 | 正常）
  · 输出 JSON 格式约定：{"label","severity","reason"}，只返回 JSON
  · severity 三档（clear/likely/unsure）的判断指引
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from .paths import REPO_ROOT as ROOT
PROMPTS_DIR = ROOT / "prompts"


def list_variants() -> List[str]:
    """列出所有可用 prompt 变体 key（供审核台下拉、benchmark 遍历）。"""
    if not PROMPTS_DIR.exists():
        return []
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.txt"))


@lru_cache(maxsize=None)
def get_prompt(variant: str) -> str:
    """按变体 key 读取 prompt 文本。找不到时回退到 'base'，再找不到则报错。"""
    path = PROMPTS_DIR / f"{variant}.txt"
    if not path.exists():
        base = PROMPTS_DIR / "base.txt"
        if base.exists():
            return base.read_text(encoding="utf-8")
        raise FileNotFoundError(
            f"prompt 变体 '{variant}' 不存在，且无 base.txt 兜底（目录：{PROMPTS_DIR}）。"
        )
    return path.read_text(encoding="utf-8")


def all_prompts() -> Dict[str, str]:
    """加载全部变体，返回 {key: text}。"""
    return {v: get_prompt(v) for v in list_variants()}
