# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 这是什么
Subtextor：图文语境违规检测的**级联流水线 + 可插拔接口框架**（不是又一个分类器）。
Python 包 `subtextor/`，Python 3.10，conda 环境。

## 最重要的一条
本仓库**无独立架构规格文档**（原 DESIGN/ARCHITECTURE 已并入实现与 README）。**以代码为准**；
对外说明见 `README.md`，不可违反的硬约束见下方「不可违反（HC）」。做架构相关改动前先读相关源码与本文 HC，别偷偷偏离立意（HC-2）。
"为什么这样选"的论证在 `Personal/面试问答准备.md`（gitignore），不要塞进 README。

## 当前状态
- **`src/` 布局**：`src/subtextor/`（含 `synth/`）、`src/apps/{api,web,cli}`、`src/ml/training/`、`src/eval/benchmark/`；`config/`、`prompts/`、`tests/` 在根目录；`pyproject.toml` 走 src 布局，依赖全集中在 `pyproject.toml`（核心 + `[ocr]`/`[dev]` 可选档）。
- **单页前端 `apps/web/index.html`**：主页（立意/同图异文示意）/ 单图测试（检测 + 级联轨迹 + 人工写回 + prompt 切换）/ 模型架构（级联漏斗静态示意）/ 模型选择（选并启动本地 llama.cpp 模型，卡片式）。**性能测试视图当前已注释隐藏**（tab/section/JS 三处）。
- **gotcha**：模型架构页的两个消融开关（初筛 / VLM）**目前仅前端视觉、未接后端**——只灰卡片，不做真实消融；接真消融需后端按 `pipeline.stages` 重跑。
- 仓库根定位统一用 `subtextor.paths.REPO_ROOT`（向上找 pyproject/config），别再写 `parent.parent` 硬算深度。

## 不可违反（HC，违反即不合格）
- **HC-1**：仓库内**永不放真实违规/NSFW 图像**。演示数据一律程序化合成；NSFW 只下模型权重。
- **HC-2**：中性视觉信号（二维码等）**只升级 VLM、绝不单独定罪**；只有确定性证据（已知恶意 URL、NSFW 高分）可硬拦。
- **HC-8 诚实**：benchmark 数字**未跑通一律标"以实测为准"，绝不编造**；AC-6 必须含纯文本 LLM baseline。

## Gotcha（容易踩）
- **缓存键 = 图像 pHash + 配文指纹**：同图不同文**不得命中**（否则违背 AC-2 立意，曾踩坑）。
- **主场景"支付截图诈骗"的路由依赖 OCR 开启**：配文干净、无二维码时，靠 OCR 抽出"支付成功"等词才升级 VLM，否则被当无信号放行漏掉。
- **mock VLM 是关键词 stub**（`vlm/mock.py`，独立的 `MOCK_FRAUD_INTENT` 词表）：能离线跑通流水线，但**真多模态增益必须用真实 VLM 复测**。
- **带重依赖的环境是 conda `subtextor`**（`conda activate subtextor`，或 `/opt/miniconda3/envs/subtextor/bin/python`；含 PIL/yaml/cv2/onnxruntime/paddleocr 等）。跑真实流水线/OCR/benchmark 用 `PYTHONPATH=src /opt/miniconda3/envs/subtextor/bin/python …`。裸 `python3` 只有标准库——核心契约测试（`tests/`）刻意纯标准库随时可跑，其余只能 `py_compile`。
- **OCR 已装（paddleocr 2.7.3 + paddlepaddle 2.6.2）**：ABI 硬约束 **numpy<2**（paddle 2.6/opencv 4.6 按 numpy 1.x 编译，升 numpy≥2 报 `multiarray failed`）；**勿升 paddleocr 3.x**（API 变，`ocr.py` 用 2.x 调用）。装法：`pip install -e ".[ocr]"`（见 `pyproject.toml` 的 `[ocr]` 档注释）。
- **L0 NSFW 已激活**：GantMan nsfwjs → `models/nsfw.onnx`（gitignore，只下权重）。`config.nsfw` 的 `layout/normalize/output_kind/nsfw_indices` **随模型而变**（GantMan=nhwc/false/probs/[1,3]=拦 hentai+porn），换模型必须同步改。**TensorFlow 仅转换期用**，运行期只用 onnxruntime。

## 跑法（src 布局：先 `pip install -e .`，或给命令前缀 `PYTHONPATH=src`）
```bash
pip install -e .                                            # 一次性，之后 import 干净
python -m apps.cli.demo --backend mock --synth              # 最小 demo（离线，四对照）
uvicorn apps.api.main:app --port 7860                       # 审核台（FastAPI 后端 + apps/web 单页前端）
python -m eval.benchmark.run_benchmark --backend mock --n 10  # AC-5/AC-6
python -m apps.cli.serve_vlm --model 2b-instruct           # 跨平台拉起本地 llama.cpp
python -m subtextor.synth.generate                         # 生成合成数据看图
```

## 改完怎么自检（无重依赖也能跑）
```bash
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m tests.test_parsing_and_routing && PYTHONPATH=src python3 -m tests.test_cache && PYTHONPATH=src python3 -m tests.test_vlm_degradation
```

## 约定
- 配置/阈值/后端/模型/prompt 全集中在 `config/default.yaml` 与 `prompts/`，**不散落代码**。
- 注释与文档用中文（与现有代码一致）；标识符用英文。
- **改 `README.md` 须同步 `README.EN.md`**（中英双语版，结构与内容保持一致）。
