# -*- coding: utf-8 -*-
"""
图标生成器（构建期工具，使用本机 Pillow）
==========================================
- 生成 Web/PWA 图标：webui/icons/icon-192.png、icon-512.png、icon-maskable-512.png
- 可选生成 Android mipmap：--android-res android/app/src/main/res

设计：蓝色圆角底 + 白色打开的书（纯几何绘制，不依赖中文字体）。
Android 启动图标为满幅（square）与圆形（round）两种。

用法：
    python tools/make_icons.py
    python tools/make_icons.py --android-res android/app/src/main/res
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw

BG = "#4f6ef7"
FG = "#ffffff"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ANDROID_MIPMAPS = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def _book(draw, size, margin_ratio):
    """在画布中央画一本打开的书"""
    m = int(size * margin_ratio)
    left, right = m, size - m
    top, bottom = int(size * 0.30), int(size * 0.72)
    mid = size // 2
    gap = max(1, size // 48)
    page_h = bottom - top
    radius = max(2, int(size * 0.04))
    line_w = max(1, int(size * 0.022))
    for x0, x1 in ((left, mid - gap), (mid + gap, right)):
        draw.rounded_rectangle([x0, top, x1, bottom], radius=radius, fill=FG)
        for k in range(3):
            y = top + int(page_h * (0.30 + 0.20 * k))
            draw.line([x0 + int(size * 0.05), y, x1 - int(size * 0.05), y], fill=BG, width=line_w)


def make_icon(size, *, maskable=False, round_icon=False):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if round_icon:
        d.ellipse([0, 0, size - 1, size - 1], fill=BG)
    elif maskable:
        d.rectangle([0, 0, size - 1, size - 1], fill=BG)          # 满幅，安全区内放内容
    else:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.18), fill=BG)
    _book(d, size, 0.20 if maskable else 0.16)
    return img


def write_web_icons():
    out_dir = os.path.join(ROOT, "webui", "icons")
    os.makedirs(out_dir, exist_ok=True)
    jobs = [
        ("icon-192.png", make_icon(192)),
        ("icon-512.png", make_icon(512)),
        ("icon-maskable-512.png", make_icon(512, maskable=True)),
    ]
    for name, img in jobs:
        path = os.path.join(out_dir, name)
        img.save(path, "PNG")
        print(f"  ✓ {os.path.relpath(path, ROOT)}  ({img.size[0]}x{img.size[1]})")


def write_android_icons(res_dir):
    for folder, size in ANDROID_MIPMAPS.items():
        d = os.path.join(res_dir, folder)
        os.makedirs(d, exist_ok=True)
        make_icon(size, maskable=True).save(os.path.join(d, "ic_launcher.png"), "PNG")
        make_icon(size, round_icon=True).save(os.path.join(d, "ic_launcher_round.png"), "PNG")
        print(f"  ✓ {os.path.relpath(d, ROOT)}/ic_launcher(.round).png ({size}px)")


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 PWA / Android 图标")
    parser.add_argument("--android-res", default="", help="Android res 目录（可选）")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("生成 Web/PWA 图标：")
    write_web_icons()
    if args.android_res:
        print("生成 Android mipmap：")
        write_android_icons(os.path.abspath(args.android_res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
