"""仓库根目录的单一来源。

config/ prompts/ data/ models/ 等都在仓库根；包却在 src/subtextor/ 下。为避免各模块用
`parent.parent` 硬算深度（迁目录就崩），统一向上找含 pyproject.toml / config 的目录。
"""

from __future__ import annotations

from pathlib import Path


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists() or (parent / "config" / "default.yaml").exists():
            return parent
    # 兜底：src/subtextor/paths.py → 仓库根是 parents[2]
    return here.parents[2]


REPO_ROOT = _find_repo_root()
