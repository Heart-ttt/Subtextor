"""FastAPI 审核台后端（Phase 4 / FR-6 / AC-4 / AC-12）。

包装级联流水线，对外提供 REST：检测、人工写回闭环、prompt 切换、模型服务管理、benchmark。
静态单页前端挂在 `/`（src/apps/web）。server 仍是独立外部进程，本服务只通过 HTTP 调它（HC-5）。

跑法（需 `pip install -e .` 或 `PYTHONPATH=src`）：
  uvicorn apps.api.main:app --host 127.0.0.1 --port 7860
  或  python -m apps.api
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from subtextor import serving
from subtextor.config import load_config
from subtextor.paths import REPO_ROOT
from subtextor.pipeline import Pipeline
from subtextor.prompts import list_variants
from subtextor.types import Label, Post

WEB_DIR = REPO_ROOT / "src" / "apps" / "web"

app = FastAPI(title="Subtextor 审核台")

# 单实例：配置、流水线、服务管理器。
_CFG = load_config()
_PIPELINE = Pipeline(_CFG)
_MGR = serving.ServerManager()
# token → (image_path, text)，供人工写回复用同一帖（避免前端重传图）。
_POSTS: dict[str, tuple] = {}


# ───────────────────────── 健康 / prompt ─────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "server": _MGR.status()}


@app.get("/api/prompts")
def prompts():
    return {"variants": list_variants() or ["base"],
            "default": _CFG.get("vlm", {}).get("prompt", "base")}


# ───────────────────────── 检测 ─────────────────────────
@app.post("/api/detect")
async def detect(
    image: UploadFile = File(...),
    text: str = Form(""),
    prompt: Optional[str] = Form(None),
):
    suffix = Path(image.filename or "u.png").suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(await image.read())
    tmp.close()
    try:
        post = Post(image=tmp.name, text=text or "", post_id="api")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    result = _PIPELINE.detect(post, prompt_variant=prompt)
    token = uuid.uuid4().hex
    _POSTS[token] = (tmp.name, text or "")
    d = result.to_dict()
    d["trace"] = result.extra.get("trace", [])
    d["token"] = token
    d["server_running"] = _MGR.is_running()
    return d


# ───────────────────────── 人工写回闭环（FR-13 / AC-11）─────────────────────────
class ReviewReq(BaseModel):
    token: str
    approved: bool


@app.post("/api/review")
def review(req: ReviewReq):
    if req.token not in _POSTS:
        return JSONResponse({"error": "token 失效，请重新检测"}, status_code=400)
    img, text = _POSTS[req.token]
    post = Post(image=img, text=text, post_id="api")
    result = _PIPELINE.record_human_decision(post, approved=req.approved, label=Label.FRAUD)
    return result.to_dict()


# ───────────────────────── 模型与服务 ─────────────────────────
@app.get("/api/models")
def models():
    presets = [
        {"key": k, "note": p["note"], "downloaded": serving.is_preset_downloaded(k)}
        for k, p in serving.PRESETS.items()
    ]
    local = [{"label": lm.label, "has_mmproj": lm.mmproj_path is not None}
             for lm in serving.list_local_gguf()]
    return {"presets": presets, "local": local, "status": _MGR.status(),
            "running": _MGR.is_running()}


class ServeReq(BaseModel):
    preset: Optional[str] = None
    model_file: Optional[str] = None  # 本地 gguf 文件名


@app.post("/api/serve/start")
def serve_start(req: ServeReq):
    if req.preset and req.preset in serving.PRESETS:
        m, mm = serving.preset_paths(req.preset)
    elif req.model_file:
        match = next((lm for lm in serving.list_local_gguf()
                      if lm.label == req.model_file), None)
        if match is None:
            return JSONResponse({"error": "本地模型未找到"}, status_code=400)
        m, mm = match.model_path, match.mmproj_path
    else:
        return JSONResponse({"error": "需指定 preset 或 model_file"}, status_code=400)
    msg = _MGR.start(m, mm)
    return {"message": msg, "status": _MGR.status()}


@app.post("/api/serve/stop")
def serve_stop():
    _MGR.stop()
    return {"status": _MGR.status()}


@app.get("/api/serve/init")
def serve_init():
    """确保本地有 llama-server 二进制（缺则下载）。"""
    logs = []
    try:
        serving.ensure_llama_server(progress=logs.append)
        return {"ok": True, "logs": logs}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e), "logs": logs}, status_code=500)


# ───────────────────────── benchmark（架构/统计）─────────────────────────
class BenchReq(BaseModel):
    n: int = 5
    mock: bool = True


@app.post("/api/benchmark")
def benchmark(req: BenchReq):
    import copy
    import sys

    # 添加 src 到 Python 路径（若未安装 pip install -e .）
    src_path = REPO_ROOT / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    from eval.benchmark.run_benchmark import _load_manifest, bench_cost, bench_joint_gain

    cfg = copy.deepcopy(_CFG)
    if req.mock:
        cfg.setdefault("vlm", {})["backend"] = "mock"
    manifest = _load_manifest(int(req.n))
    return {"cost": bench_cost(cfg, manifest), "gain": bench_joint_gain(cfg, manifest)}


# ───────────────────────── 对照样例（同图不同文，演示 AC-2）─────────────────────────
@app.get("/api/examples")
def examples():
    from subtextor.synth.generate import build_contrast_pair

    data_root = (REPO_ROOT / "data").resolve()
    out = []
    for title, post in build_contrast_pair():
        rel = Path(post.image).resolve().relative_to(data_root)
        out.append({"title": title, "image": f"/data/{rel.as_posix()}", "text": post.text})
    return out


# ───────────────────────── 静态前端 ─────────────────────────
@app.get("/")
def index():
    idx = WEB_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return JSONResponse({"hint": "前端尚未生成（Phase 4 进行中）；API 在 /api/* 可用。"})


(REPO_ROOT / "data").mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(REPO_ROOT / "data")), name="data")
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
