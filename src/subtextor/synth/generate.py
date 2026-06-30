"""程序化合成演示样本（FR-10 / HC-1 / AC-2 / AC-8 训练数据）。

能力：
  · 合成二维码图（qrcode 库）贴入随机背景 → 诈骗类素材，自动得标注（含/不含二维码）。
  · 合成人物占位图（PIL 画的抽象头像，非真实人物）→ 网暴类素材。
  · 配以 templates.py 的话术，组成 违规 / 正常 / 对照 三种样本。
  · 输出 manifest.json（每个样本的 image 路径与 label），供 benchmark 使用。

合规（HC-1）：零真实违规图像、零版权风险，全部即时生成。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import List, Tuple

from subtextor.types import Label, Post
from subtextor.paths import REPO_ROOT as ROOT

from . import templates
OUT_DIR = ROOT / "data" / "synth"


def _random_bg(size=(256, 256)):
    from PIL import Image

    color = tuple(random.randint(180, 255) for _ in range(3))
    return Image.new("RGB", size, color)


def make_qr_image(payload: str = "https://example.com/group", size=(256, 256)):
    """生成一张二维码贴在随机背景上的图（中性素材）。"""
    import qrcode
    from PIL import Image

    qr = qrcode.make(payload).convert("RGB")
    bg = _random_bg(size)
    qr_size = random.randint(120, 180)
    qr = qr.resize((qr_size, qr_size))
    x = random.randint(0, size[0] - qr_size)
    y = random.randint(0, size[1] - qr_size)
    bg.paste(qr, (x, y))
    return bg


def make_person_placeholder(size=(256, 256)):
    """生成一张抽象'人物'占位图（圆头+肩，非任何真实人物，HC-1）。"""
    from PIL import Image, ImageDraw

    bg = _random_bg(size)
    d = ImageDraw.Draw(bg)
    cx, cy = size[0] // 2, size[1] // 2
    skin = (random.randint(200, 240), random.randint(170, 210), random.randint(150, 190))
    d.ellipse([cx - 40, cy - 70, cx + 40, cy + 10], fill=skin)          # 头
    d.ellipse([cx - 70, cy + 20, cx + 70, cy + 140], fill=skin)         # 肩
    return bg


def make_plain_image(size=(256, 256)):
    """无二维码的普通图（作为检测器训练的负样本）。"""
    from PIL import Image, ImageDraw

    bg = _random_bg(size)
    d = ImageDraw.Draw(bg)
    for _ in range(random.randint(2, 6)):
        box = [random.randint(0, size[0]) for _ in range(2)]
        box += [box[0] + random.randint(10, 60), box[1] + random.randint(10, 60)]
        d.rectangle(box, fill=tuple(random.randint(0, 255) for _ in range(3)))
    return bg


def _font(size: int):
    """尽量取一个能渲染中文的字体；失败则用 PIL 默认（英文/数字仍可读）。"""
    from PIL import ImageFont

    for path in (
        "/System/Library/Fonts/PingFang.ttc",          # macOS 中文
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "C:/Windows/Fonts/msyh.ttc",                    # Windows 微软雅黑
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_payment_screenshot(amount: int = None, size=(300, 380)):
    """合成一张"支付成功"风格的手机截图（明确合成、无真实品牌/商标，HC-1）。

    图像本身就是诈骗道具：'支付成功 ¥金额' 的界面 + 催发货话术 = 交易诈骗。
    只有 VLM 看图才懂"这是张（伪造）支付截图"，纯文本判不了（DESIGN §3.1 / 硬伤①）。
    """
    from PIL import Image, ImageDraw

    amount = amount if amount is not None else random.choice([199, 299, 588, 1280, 2000])
    img = Image.new("RGB", size, (245, 246, 248))
    d = ImageDraw.Draw(img)
    # 顶部状态栏 + 白卡
    d.rectangle([0, 0, size[0], 28], fill=(255, 255, 255))
    d.rounded_rectangle([20, 60, size[0] - 20, size[1] - 40], radius=14, fill=(255, 255, 255))
    # 绿色对勾圆
    cx, cy = size[0] // 2, 130
    d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=(7, 193, 96))
    d.line([cx - 16, cy, cx - 4, cy + 14], fill="white", width=6)
    d.line([cx - 4, cy + 14, cx + 18, cy - 12], fill="white", width=6)
    # 文案
    d.text((cx, 185), "支付成功", fill=(40, 40, 40), font=_font(22), anchor="mm")
    d.text((cx, 230), f"¥ {amount}.00", fill=(20, 20, 20), font=_font(30), anchor="mm")
    for i, line in enumerate(["收款方  个人商户", "支付方式  余额", "交易时间  刚刚"]):
        d.text((45, 275 + i * 28), line, fill=(150, 150, 150), font=_font(14))
    return img


def make_official_poster(size=(300, 380)):
    """合成一张"官方活动"风格海报（仿冒载体）+ 一个二维码。无真实品牌（HC-1）。"""
    from PIL import Image, ImageDraw

    hue = random.choice([(214, 48, 49), (9, 132, 227), (108, 92, 231), (225, 112, 85)])
    img = Image.new("RGB", size, hue)
    d = ImageDraw.Draw(img)
    d.text((size[0] // 2, 50), "官方福利活动", fill="white", font=_font(26), anchor="mm")
    d.text((size[0] // 2, 95), "扫 码 领 取", fill=(255, 240, 180), font=_font(20), anchor="mm")
    # 贴一个二维码
    try:
        import qrcode

        qr = qrcode.make("https://example.com/promo").convert("RGB").resize((150, 150))
        img.paste(qr, ((size[0] - 150) // 2, 150))
    except Exception:
        d.rectangle([75, 150, 225, 300], fill="white")
    d.text((size[0] // 2, 330), "名额有限 先到先得", fill="white", font=_font(16), anchor="mm")
    return img


def build_contrast_pair() -> List[Tuple[str, Post]]:
    """构造"同一张图、不同配文语境 → 相反判定"的对照对（AC-2 立意验证核心）。

    v2 用"伪造支付截图"作主对照：图像本身是诈骗道具，纯文本判不了、必须看图——
    最能体现多模态 VLM 的不可替代性（DESIGN §3.1）。同时保留二维码对照作次场景。
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pay_path = OUT_DIR / "contrast_payment.png"
    make_payment_screenshot().save(pay_path)
    qr_path = OUT_DIR / "contrast_qr.png"
    make_qr_image().save(qr_path)

    return [
        ("对照 A：伪造支付截图 + 催发货话术（期望→诈骗导流/拦截）",
         Post(image=str(pay_path), text=templates.PAYMENT_FRAUD_CAPTIONS[0], post_id="contrast_pay_fraud")),
        ("对照 B：同一张支付截图 + 正常记账语境（期望→正常/放行）",
         Post(image=str(pay_path), text=templates.PAYMENT_NORMAL_CAPTIONS[0], post_id="contrast_pay_normal")),
        ("对照 C：二维码 + 诈骗话术（次场景，期望→诈骗导流/拦截）",
         Post(image=str(qr_path), text=templates.FRAUD_CAPTIONS[0], post_id="contrast_qr_fraud")),
        ("对照 D：同一张二维码 + 正常点单语境（期望→正常/放行）",
         Post(image=str(qr_path), text=templates.NORMAL_QR_CAPTIONS[0], post_id="contrast_qr_normal")),
    ]


def generate_dataset(n_each: int = 10, seed: int = 0) -> dict:
    """生成完整演示数据集并写 manifest.json。

    覆盖：诈骗(违规) / 网暴(违规) / 二维码正常对照 / 人物正常对照 / 纯图正常。
    返回 manifest（也落盘到 data/synth/manifest.json）。
    """
    random.seed(seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    samples = []

    def _save(img, name):
        p = OUT_DIR / name
        img.save(p)
        return str(p.relative_to(ROOT))

    for i in range(n_each):
        # 主场景·诈骗：伪造支付截图 + 催发货话术（图像即道具，img_prop=True）
        samples.append({
            "image": _save(make_payment_screenshot(), f"pay_fraud_{i}.png"),
            "text": random.choice(templates.PAYMENT_FRAUD_CAPTIONS),
            "label": Label.FRAUD.value, "has_qr": False, "img_prop": True,
        })
        # 主场景·对照正常：同类支付截图 + 正常记账（支撑 AC-2）
        samples.append({
            "image": _save(make_payment_screenshot(), f"pay_normal_{i}.png"),
            "text": random.choice(templates.PAYMENT_NORMAL_CAPTIONS),
            "label": Label.NORMAL.value, "has_qr": False, "img_prop": True,
        })
        # 主场景·诈骗：仿冒官方海报 + 导流话术
        samples.append({
            "image": _save(make_official_poster(), f"poster_fraud_{i}.png"),
            "text": random.choice(templates.POSTER_FRAUD_CAPTIONS),
            "label": Label.FRAUD.value, "has_qr": True, "img_prop": True,
        })
        # 次场景·诈骗：二维码 + 诈骗话术
        samples.append({
            "image": _save(make_qr_image(), f"qr_fraud_{i}.png"),
            "text": random.choice(templates.FRAUD_CAPTIONS),
            "label": Label.FRAUD.value, "has_qr": True, "img_prop": False,
        })
        # 次场景·对照正常：二维码 + 正常点单
        samples.append({
            "image": _save(make_qr_image(), f"qr_normal_{i}.png"),
            "text": random.choice(templates.NORMAL_QR_CAPTIONS),
            "label": Label.NORMAL.value, "has_qr": True, "img_prop": False,
        })
        # 正常：纯图无配文（无任何钩子，初筛应直接放行）
        samples.append({
            "image": _save(make_plain_image(), f"normal_plain_{i}.png"),
            "text": "",
            "label": Label.NORMAL.value, "has_qr": False, "img_prop": False,
        })

    manifest = {"root": str(ROOT), "count": len(samples), "samples": samples}
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    m = generate_dataset()
    print(f"已生成 {m['count']} 个合成样本 → {OUT_DIR}")
