<h1 align="center">Subtextor · Image–Text Context Moderation Cascade</h1>


<h3 align="center">
  <i>"The image keeps its silence, the words feign careless ease;<br>where the two leave their trace, a hidden subtext hides — on the verge of speech, then gone."</i>
</h3>

<p align="center">
  <a href="https://github.com/Heart-ttt/Subtextor/releases">
    <img alt="GitHub Release" src="https://img.shields.io/github/v/release/Heart-ttt/Subtextor?color=blue&logo=github">
  </a>
  <a href="./LICENSE">
    <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
  </a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white">
</p>

<p align="center">
  <a href="README.md">简体中文</a>
  ·
  <a href="README.EN.md">English</a>
  <br>
  <a href="#quick-start">Quick Start</a>
</p>

## Table of Contents

- [Introduction](#introduction)
- [Detection Examples](#detection-examples)
- [Features](#features)
- [Architecture](#architecture)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)

## Introduction

In content moderation, the real headache is rarely the blatant violation — it's the subtle, adversarial cases where **"each part looks fine, but together they're a trap."** A scenic photo paired with a lure can be a scam; an innocent *"has it shipped yet?"* attached to a forged payment screenshot becomes fraud.

This **mismatch between image and text context** is the blind spot of traditional moderation:

- **Pure CNNs** — can't read the "subtext" inside an image
- **Keyword lists** — can't keep up with endlessly mutating phrasings
- **Text-only LLMs** — are blind to the key props *inside* the image (QR codes, fake screenshots)

Only a **multimodal model (VLM) that jointly understands image and text** can truly "get the joke." But VLMs are slow and expensive — running one on every post isn't realistic.

**Subtextor's approach**: a cascade pipeline that spends the VLM only where it counts, filtering like a funnel —

1. **Front-line filtering** — cheap rules, OCR and vision models absorb the vast majority of traffic, clearing the obvious blacks and whites first
2. **Precision strike** — only the hard cases (complex image–text relationships that must be understood jointly) go to the VLM for deep reasoning
3. **Closed-loop feedback** — emit explainable verdicts and write human reviews back to the cache, so the system gets smarter the more it is used

> [!IMPORTANT]
> **Core principle**: a neutral visual signal (e.g. a QR code) may only act as a clue that **escalates** a decision — never grounds for a verdict on its own. Real precision means confirming malice from context.

## Detection Examples

> [!NOTE]
> Real screenshots from the moderation console: one cascade pipeline handling different post types, each with a verdict, a reason, and a cascade trace. Three fraud variants blocked, the normal post allowed.

### Fraud examples
---
<p align="center">
  <img src="attachments/exp1.png" alt="QR lead-gen scam → blocked" width="100%">
</p>
<p align="center"><em>▲ QR lead-gen scam — "day-rate part-time, ¥300+/day" + a group QR → prefilter escalates to VLM → <strong>Fraud / Lead-gen · Blocked</strong></em></p>

<br>

<p align="center">
  <img src="attachments/exp2.png" alt="Forged payment screenshot urging shipment → blocked" width="100%">
</p>
<p align="center"><em>▲ Forged payment screenshot urging shipment — faking a successful payment to make the seller ship first → suspicious text escalates to VLM → <strong>Fraud / Lead-gen · Blocked</strong></em></p>

<br>

<p align="center">
  <img src="attachments/exp3.png" alt="Fake official giveaway poster → blocked" width="100%">
</p>
<p align="center"><em>▲ Fake "official" giveaway poster — "official perk · limited time" + QR + "everyone hurry" → escalates to VLM → <strong>Fraud / Lead-gen · Blocked</strong></em></p>

### Normal control
---

<p align="center">
  <img src="attachments/exp4.png" alt="Normal post → allowed" width="100%">
</p>
<p align="center"><em>▲ Normal control — a weekend coffee-market poster, no QR, no lure → prefilter directly <strong>Normal · Allowed</strong></em></p>

## Features

### Detection & decision

| Feature | What it does |
|---------|--------------|
| **Four-stage cascade** | Cache → Prefilter → VLM → Human: cheap layers carry the load, and only the genuinely uncertain few summon the expensive multimodal model |
| **Joint image–text decision (VLM)** | Sends image, caption, and OCR-extracted text together to a vision-capable LLM to read the true intent behind the post, returning label + severity + reason |
| **QR decoding** | Decodes a QR's payload (URL / vCard / text) as a neutral clue that escalates the decision — **never a verdict on its own** |
| **NSFW visual hard-block** | Pretrained model → ONNX; explicit imagery is deterministic visual evidence and is blocked directly |
| **URL reputation check** | Checks URLs (from the QR + the caption) against a known-malicious list; a hit is a hard block; the backend is pluggable |
| **In-image OCR** | Reads text printed inside the image into the caption (payment-screenshot scams route to the VLM via this step) |
| **Explainable verdicts** | Every result carries a human-readable reason + a full cascade trace (which stage, and why) |

### Engineering & usability

| Feature | What it does |
|---------|--------------|
| **Pluggable backends** | The VLM speaks the OpenAI-compatible protocol; switch local llama.cpp / remote API / mock with a single config line, without touching the core logic |
| **Human closed loop** | Pending → human approve / reject → written back to the cache; the same image + caption reuses the human verdict next time |
| **Approximate cache** | Image pHash + caption fingerprint joint key; tolerates compression / scaling / watermarks; the same image with a **different caption does not hit** |
| **Hot-swappable prompts** | The review stance (strict / lenient / fraud-focused) lives in separate files and is switchable at runtime |
| **Reproducible evaluation** | Cascade cost savings (AC-5) + four-way recall comparison: joint vs. text-only vs. image-only (AC-6) |
| **Self-built console** | A single page with four views: Home / Single-image test / Architecture / Model selection |

## Architecture

A **cascade funnel**: cheap layers absorb the traffic and filter level by level, reserving the expensive VLM only for the few posts that truly require joint image–text understanding; any level can short-circuit early, and human verdicts are written back to form a closed loop.
<p align="center">
  <img src="attachments/模型架构图.png" alt="Architecture" width="100%">
</p>

## Screenshots

<p align="center">
  <img src="attachments/主页.png" alt="Home" width="100%">
</p>
<p align="center"><em>▲ Home — the thesis in one screen: same image, different caption, opposite verdict</em></p>

<br>

<p align="center">
  <img src="attachments/单图测试.png" alt="Single-image test" width="100%">
</p>
<p align="center"><em>▲ Single-image test — detection + cascade trace + human approve / reject write-back</em></p>

<br>

<p align="center">
  <img src="attachments/模型架构.png" alt="Architecture view" width="100%">
</p>
<p align="center"><em>▲ Architecture — the cascade funnel: each level only handles what the previous one left behind</em></p>

<br>

<p align="center">
  <img src="attachments/模型选择.png" alt="Model selection" width="100%">
</p>
<p align="center"><em>▲ Model selection — download and start a local llama.cpp model</em></p>

## Quick Start

### 1. Install

```bash
conda activate subtextor          # or first time: conda env create -f environment.yml
pip install -e .                  # editable install (src layout); imports stay clean afterward
```

> Not installed yet? Prefix a command with `PYTHONPATH=src` to run it ad hoc.

### 2. Run offline (no model required)

```bash
python -m apps.cli.demo --backend mock --synth
```

Prints verdicts for a set of "same image, different caption" contrast samples — the project's whole thesis: **same image, different caption, opposite verdict.**

### 3. Launch the console

```bash
uvicorn apps.api.main:app --port 7860   # open http://127.0.0.1:7860 in your browser
```

In **Model selection**, click **Initialize runtime** and start a local model (e.g. `2b-instruct`); then in **Single-image test** load a contrast sample and click **Detect** to see the cascade trace and the joint verdict. A **Pending** result can be approved / rejected in one click and written back to close the loop.

## License

Released under the [MIT License](./LICENSE).
