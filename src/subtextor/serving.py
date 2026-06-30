"""VLM server 供给与生命周期管理（跨平台、免 brew）。

被 CLI（apps/cli/serve_vlm.py）与 FastAPI 审核台（apps/api）共用。职责：
  · ensure_llama_server()  —— 按 OS/架构下载官方预编译 llama-server（GitHub Releases）。
  · download_preset_iter() —— 从 Hugging Face 下载所选 Qwen3-VL 的 GGUF + mmproj（带进度）。
  · list_local_gguf()      —— 识别用户自己放进 models/ 的 GGUF（模型 + mmproj 配对）。
  · ServerManager          —— 启动/停止/查询 llama-server 子进程，暴露 OpenAI 兼容端点。

设计：server 始终是独立外部进程，流水线只通过 OpenAI 兼容 HTTP 与它通信（HC-5）。
只用标准库，无需先 pip 安装任何 ML 包。
"""

from __future__ import annotations

import atexit
import json
import platform
import re
import stat
import subprocess
import time
import os
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Tuple

from .paths import REPO_ROOT as ROOT
VENDOR_DIR = ROOT / ".llama"      # 预编译 llama.cpp 二进制缓存
MODELS_DIR = ROOT / "models"      # GGUF 存放处（已在 .gitignore）

GITHUB_LATEST = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
# HF 下载域名可用环境变量覆盖（国内可设 HF_ENDPOINT=https://hf-mirror.com）。
HF_BASE = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
_UA = {"User-Agent": "subtextor-serve/1.0"}

# urllib 默认只认 http(s)_proxy，不认 SOCKS。若设了 SOCKS 代理且需经它访问外网，
# 下载会绕不过去——优先用 HF 镜像（HF_ENDPOINT），或另设 http(s)_proxy。

# Qwen3-VL Instruct 预设（命名规律已对照官方仓库核实；某文件 404 时会提示到仓库核对）。
# 只用 Instruct：低延迟、适合审核台演示；不用 Thinking 档（先推理再答、更慢）。
PRESETS = {
    "2b-instruct": {"repo": "Qwen/Qwen3-VL-2B-Instruct-GGUF",
                    "model": "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
                    "mmproj": "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
                    "note": "边缘演示档 · 约 1.1GB · 最快"},
    "4b-instruct": {"repo": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
                    "model": "Qwen3VL-4B-Instruct-Q4_K_M.gguf",
                    "mmproj": "mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf",
                    "note": "均衡档 · 约 2.5GB"},
    "8b-instruct": {"repo": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
                    "model": "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
                    "mmproj": "mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf",
                    "note": "更强判别档 · 约 5GB"},
}

ProgressFn = Callable[[str], None]


# ============================================================ 下载工具
def _download_iter(url: str, dest: Path, label: str = "") -> Iterator[str]:
    """流式下载 dest（先 .part 再改名，已存在则跳过），yield 人类可读进度串。"""
    label = label or dest.name
    if dest.exists() and dest.stat().st_size > 0:
        yield f"✓ 已存在，跳过 {label}"
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        last_pct = -5
        chunk = 1 << 20
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            f.write(buf)
            read += len(buf)
            if total:
                pct = read * 100 // total
                if pct - last_pct >= 5:
                    last_pct = pct
                    yield f"↓ {label}  {read >> 20}/{total >> 20} MiB ({pct}%)"
            else:
                yield f"↓ {label}  {read >> 20} MiB"
    tmp.rename(dest)
    yield f"✓ 完成 {label}"


# ============================================================ llama.cpp 二进制
def _select_asset(assets: List[dict]) -> Optional[dict]:
    """从 release 资产里按当前平台挑一个通用 llama-server 包。

    注意命名：macOS/Linux 为 .tar.gz，Windows 为 .zip；并排除 cudart-* 等非 llama-server
    包，Windows 优先 CPU（其次 vulkan），避免误选需要特定驱动的 cuda/hip/sycl。
    """
    sysname = platform.system().lower()
    machine = platform.machine().lower()
    # 只在以 llama- 开头的资产里挑，排除 cudart-llama-* 这类运行时附属包。
    cand = [a for a in assets if a["name"].startswith("llama-")]

    def pick(patterns: List[str]) -> Optional[dict]:
        for pat in patterns:
            for a in cand:
                if re.search(pat, a["name"]):
                    return a
        return None

    if sysname == "darwin":
        if machine in ("arm64", "aarch64"):       # Apple Silicon（含 M5）+ Metal
            return pick([r"bin-macos-arm64\.(tar\.gz|zip)$"])
        return pick([r"bin-macos-x64\.(tar\.gz|zip)$"])
    if sysname == "windows":
        return pick([
            r"bin-win-cpu-x64\.zip$",             # 优先：纯 CPU，最通用
            r"bin-win-vulkan-x64\.zip$",          # 次选：通用 GPU
            r"bin-win-cpu-arm64\.zip$",
        ])
    if sysname == "linux":
        if machine in ("aarch64", "arm64"):
            return pick([r"bin-ubuntu-arm64\.tar\.gz$"])
        return pick([r"bin-ubuntu-x64\.tar\.gz$", r"bin-linux-.*x64\.tar\.gz$"])
    return None


def _extract_archive(archive: Path, dest: Path) -> None:
    """解压 .zip 或 .tar.gz 到 dest。"""
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    elif name.endswith((".tar.gz", ".tgz", ".tar")):
        import tarfile
        with tarfile.open(archive) as tf:
            tf.extractall(dest)
    else:
        raise RuntimeError(f"未知压缩格式：{archive.name}")


def find_llama_server() -> Optional[Path]:
    exe = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    found = list(VENDOR_DIR.rglob(exe))
    return found[0] if found else None


def ensure_llama_server(progress: Optional[ProgressFn] = None) -> Path:
    """确保本地有 llama-server，返回其路径。初始化时调用。"""
    def emit(msg: str):
        if progress:
            progress(msg)

    existing = find_llama_server()
    if existing:
        emit(f"✓ 已就绪 llama-server：{existing}")
        return existing

    emit("· 获取官方预编译 llama.cpp（GitHub Releases）…")
    with urllib.request.urlopen(urllib.request.Request(GITHUB_LATEST, headers=_UA)) as resp:
        release = json.load(resp)
    asset = _select_asset(release.get("assets", []))
    if asset is None:
        names = ", ".join(a["name"] for a in release.get("assets", []))
        raise RuntimeError(f"未找到匹配本平台的 release 资产。可用：{names}")

    archive_path = VENDOR_DIR / asset["name"]
    for msg in _download_iter(asset["browser_download_url"], archive_path, f"llama.cpp {release.get('tag_name','')}"):
        emit(msg)
    emit(f"· 解压 {asset['name']} …")
    _extract_archive(archive_path, VENDOR_DIR)

    server = find_llama_server()
    if server is None:
        raise RuntimeError(f"解压后未找到 llama-server，请检查 {VENDOR_DIR}。")
    if platform.system() != "Windows":
        server.chmod(server.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        if platform.system() == "Darwin":
            subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(VENDOR_DIR)], check=False)
    emit(f"✓ llama-server 就绪：{server}")
    return server


# ============================================================ 模型
def preset_paths(preset_key: str) -> Tuple[Path, Path]:
    p = PRESETS[preset_key]
    return MODELS_DIR / p["model"], MODELS_DIR / p["mmproj"]


def is_preset_downloaded(preset_key: str) -> bool:
    m, mm = preset_paths(preset_key)
    return m.exists() and mm.exists()


def download_preset_iter(preset_key: str) -> Iterator[str]:
    """下载某预设的模型 + mmproj，yield 进度串。"""
    if preset_key not in PRESETS:
        yield f"✗ 未知预设：{preset_key}"
        return
    p = PRESETS[preset_key]
    m_path, mm_path = preset_paths(preset_key)
    try:
        yield from _download_iter(f"{HF_BASE}/{p['repo']}/resolve/main/{p['model']}?download=true", m_path, p["model"])
        yield from _download_iter(f"{HF_BASE}/{p['repo']}/resolve/main/{p['mmproj']}?download=true", mm_path, p["mmproj"])
    except urllib.error.HTTPError as e:
        yield f"✗ 下载失败（HTTP {e.code}）。请到 {HF_BASE}/{p['repo']} 核对文件名后改 PRESETS。"


@dataclass
class LocalModel:
    """一个可启动的本地模型（预设已下载，或用户自放的 GGUF）。"""
    label: str
    model_path: Path
    mmproj_path: Optional[Path]


def list_local_gguf() -> List[LocalModel]:
    """扫描 models/，把模型 GGUF 与 mmproj 配对，列出可启动项（支持用户自放）。"""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    files = list(MODELS_DIR.glob("*.gguf"))
    mmprojs = [f for f in files if f.name.lower().startswith("mmproj")]
    models = [f for f in files if not f.name.lower().startswith("mmproj")]

    out: List[LocalModel] = []
    for m in sorted(models):
        # 优先按文件名匹配同名 mmproj（mmproj-<同 stem>），否则回退到唯一的那个。
        match = next((p for p in mmprojs if m.stem in p.stem or p.stem.replace("mmproj-", "") in m.stem), None)
        if match is None and len(mmprojs) == 1:
            match = mmprojs[0]
        out.append(LocalModel(label=m.name, model_path=m, mmproj_path=match))
    return out


# ============================================================ 服务进程管理
class ServerManager:
    """管理 llama-server 子进程（启动/停止/状态）。单实例即可。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = int(port)
        self._proc: Optional[subprocess.Popen] = None
        self._current: str = ""
        atexit.register(self.stop)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> str:
        if self.is_running():
            return f"● 运行中：{self._current}  →  {self.base_url}"
        return "○ 未运行"

    def start(self, model_path: Path, mmproj_path: Optional[Path], ngl: int = 99) -> str:
        if mmproj_path is None:
            return "✗ 缺少 mmproj 投影文件，无法启动多模态。请把对应 mmproj-*.gguf 放入 models/。"
        server = find_llama_server()
        if server is None:
            return "✗ 尚未就绪 llama-server，请先初始化（或调用 ensure_llama_server）。"
        self.stop()
        cmd = [
            str(server), "-m", str(model_path), "--mmproj", str(mmproj_path),
            "--host", self.host, "--port", str(self.port), "--jinja", "-ngl", str(ngl),
        ]
        VENDOR_DIR.mkdir(parents=True, exist_ok=True)
        log = open(VENDOR_DIR / "server.log", "w")
        self._proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        self._current = Path(model_path).name
        return f"· 已启动 {self._current}（日志：{VENDOR_DIR/'server.log'}）；端点 {self.base_url}"

    def wait_ready(self, timeout: float = 120) -> bool:
        """轮询 /health 直到就绪或超时。"""
        url = f"http://{self.host}:{self.port}/health"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_running():
                return False
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(1)
        return False

    def stop(self) -> str:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        return "○ 已停止"
