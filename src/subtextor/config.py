"""配置加载（FR-8 / NFR-3：阈值、后端、模型、prompt 集中管理，不散落代码里）。

默认从 config/default.yaml 读取；可用环境变量 SUBTEXTOR_CONFIG 覆盖路径，
或在调用处传入 overrides 字典做运行时覆盖（如审核台切换 prompt 侧重点）。
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Optional

# 仓库根目录 = 本文件上溯两级（subtextor/ 的父目录）。
from .paths import REPO_ROOT as ROOT

DEFAULT_CONFIG_PATH = ROOT / "config" / "default.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并 override 进 base（override 优先），返回新字典。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Optional[str] = None, overrides: Optional[dict] = None) -> dict:
    """加载配置文件并应用覆盖。

    path:      配置文件路径；默认 config/default.yaml，可被环境变量 SUBTEXTOR_CONFIG 覆盖。
    overrides: 运行时覆盖（最高优先级），如 {"vlm": {"backend": "mock"}}。
    """
    try:
        import yaml  # 延迟导入：仅在真正加载配置时需要 PyYAML。
    except ImportError as e:  # pragma: no cover
        raise ImportError("加载配置需要 PyYAML，请先 `pip install pyyaml`。") from e

    cfg_path = Path(path or os.environ.get("SUBTEXTOR_CONFIG", DEFAULT_CONFIG_PATH))
    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在：{cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f) or {}

    if overrides:
        cfg = _deep_merge(cfg, overrides)

    # 把仓库根目录注入配置，便于各模块解析相对路径。
    cfg.setdefault("_root", str(ROOT))
    return cfg


def resolve_path(cfg: dict, p: str) -> Path:
    """把配置里的相对路径解析为相对仓库根目录的绝对路径。"""
    path = Path(p)
    if path.is_absolute():
        return path
    return Path(cfg.get("_root", ROOT)) / path
