#!/usr/bin/env python3
"""跨平台 llama.cpp VLM server 启动器（CLI，免 brew，Win/macOS/Linux 通用）。

核心逻辑在 subtextor/serving.py（与 FastAPI 审核台共用）。本脚本是它的命令行薄封装。
若想要网页化的"选择/下载/启停"界面，用 `uvicorn apps.api.main:app` 审核台的「模型与服务」区。

用法：
  python scripts/serve_vlm.py                      # 默认 8b-instruct，端口 8080
  python scripts/serve_vlm.py --model 2b-instruct  # 边缘演示档，最快
  python scripts/serve_vlm.py --list               # 列出预设与本地已有 GGUF
  python scripts/serve_vlm.py --only-fetch         # 只下载，不启动
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直跑（未 pip install -e .）：把 src/ 加入 import 路径，使 subtextor 可导入。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/apps/cli → src

from subtextor import serving


def main() -> None:
    ap = argparse.ArgumentParser(description="跨平台 llama.cpp VLM server 启动器（CLI）")
    ap.add_argument("--model", default="8b-instruct", choices=list(serving.PRESETS), help="模型预设")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default="8080")
    ap.add_argument("--ngl", type=int, default=99, help="offload 到 GPU 的层数（CPU 包忽略）")
    ap.add_argument("--list", action="store_true", help="列出预设与本地 GGUF 后退出")
    ap.add_argument("--only-fetch", action="store_true", help="只下载，不启动")
    args = ap.parse_args()

    if args.list:
        print("== 预设 ==")
        for k, p in serving.PRESETS.items():
            mark = "✓已下载" if serving.is_preset_downloaded(k) else "·未下载"
            print(f"  {k:14s} {mark}  {p['note']}  ({p['repo']})")
        print("== 本地 models/ 中的 GGUF ==")
        for lm in serving.list_local_gguf():
            mm = lm.mmproj_path.name if lm.mmproj_path else "（缺 mmproj）"
            print(f"  {lm.label}  + {mm}")
        return

    serving.ensure_llama_server(progress=print)
    for msg in serving.download_preset_iter(args.model):
        print(msg)
    m_path, mm_path = serving.preset_paths(args.model)

    if args.only_fetch:
        print(f"\n· 仅下载完成。模型：{m_path}\n  mmproj：{mm_path}")
        return

    mgr = serving.ServerManager(host=args.host, port=args.port)
    print(mgr.start(m_path, mm_path, ngl=args.ngl))
    print(f"\n  端点：{mgr.base_url}  （config/default.yaml 已默认指向此处）")
    print("  另开终端：python -m subtextor.demo --backend llamacpp --synth\n")
    print("  正在等待模型加载就绪（首次较慢）… Ctrl-C 退出。")
    try:
        if mgr.wait_ready(timeout=600):
            print("● server 就绪。")
        # 保持前台存活，直到用户中断。
        while mgr.is_running():
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n" + mgr.stop())


if __name__ == "__main__":
    main()
