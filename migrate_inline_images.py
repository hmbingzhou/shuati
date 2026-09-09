# -*- coding: utf-8 -*-
"""
行内图片双轨迁移：正文中的裸 token 按位置归位
==============================================
规则（针对每道带图题）：
- 自成一行、或位于整段文字末尾的图片 token → 移出正文，进入 images（题后配图）；
- 夹在句子中间的 token → 保留行内位置，包成方括号标记 [路径]；
- 选项文本里的 token → 统一包成 [路径]（选项图随选项文字内嵌显示）；
- 幂等：已是 [路径] 的不再改动。

用法：python migrate_inline_images.py [--dry-run]
"""

import datetime
import json
import os
import re
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")

USER_DATA_FILES = {"records.json", "wrong_book.json", "recycle_bin.json",
                   "exams.json", "brush_progress.json"}

from models.question import BRACKET_IMG_RE  # noqa: E402
_BARE = re.compile(
    r"[A-Za-z0-9_\u4e00-\u9fff./-]+\.(?:png|jpe?g|gif|bmp|webp)", re.IGNORECASE)


def _ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _log(msg=""):
    print(msg)


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _subject_files():
    out = []
    if os.path.isdir(DATA_DIR):
        for name in sorted(os.listdir(DATA_DIR)):
            if name.lower().endswith(".json") and name not in USER_DATA_FILES and not name.startswith("."):
                out.append(os.path.join(DATA_DIR, name))
    return out


def _mask_brackets(text):
    return BRACKET_IMG_RE.sub(lambda m: " " * (m.end() - m.start()), text)


def convert_text(text, collect_tail=True):
    """
    题干文本转换：
    返回 (新text, moved[list], inline[list])
    moved：移出正文进题后配图的路径（按出现顺序）
    inline：仍需以 [路径] 内嵌出现的路径
    """
    text = text or ""
    masked = _mask_brackets(text)
    matches = list(_BARE.finditer(masked))
    if not matches:
        return text, [], []
    moved, inline = [], []
    # 先收集所有需要处理的 token（decision）
    decisions = []
    for m in matches:
        pos = m.start()
        token = m.group(0)
        line_start = text.rfind("\n", 0, pos) + 1
        line_end = text.find("\n", pos)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        tail = text[m.end():].strip() == "" or line.strip() == token
        decisions.append((m.start(), m.end(), token, tail))
    # 重建文本
    out = []
    last = 0
    for s, e, token, tail in decisions:
        out.append(text[last:s])
        if collect_tail and tail:
            moved.append(token)
        else:
            inline.append(token)
            out.append(f"[{token}]")
        last = e
    out.append(text[last:])
    return "".join(out), moved, inline


def convert_option(text):
    """选项文本：裸 token 一律包成 [路径]（已带 [ ] 的不动）"""
    text = text or ""
    masked = _mask_brackets(text)
    parts, last = [], 0
    for m in _BARE.finditer(masked):
        parts.append(text[last:m.start()])
        parts.append(f"[{text[m.start():m.end()]}]")
        last = m.end()
    parts.append(text[last:])
    return "".join(parts)


def run(dry_run: bool = True):
    _log("=" * 60)
    _log(" 行内图片双轨迁移（尾部/独立行→题后 images；句中→[路径]）"
         + ("（试运行）" if dry_run else ""))
    _log("=" * 60)

    total_changed = total_moved = 0
    text_map = {}
    plans = []
    for path in _subject_files():
        subject = os.path.splitext(os.path.basename(path))[0]
        data = _load(path, None)
        if not isinstance(data, list):
            continue
        sub_map = {}
        changed_q = moved_q = 0
        for entry in data:
            old_text = entry.get("text", "")
            new_text, moved, inline = convert_text(old_text)
            opts = entry.get("options")
            # 选项文本转 [路径]
            opts_changed = False
            if isinstance(opts, list):
                for o in opts:
                    if isinstance(o, (list, tuple)) and len(o) >= 2:
                        nt = convert_option(str(o[1]))
                        if nt != o[1]:
                            o[1] = nt
                            opts_changed = True
                    elif isinstance(o, str):
                        nt = convert_option(o)
                        if nt != o:
                            opts_changed = True
            if new_text == old_text and not moved and not inline and not opts_changed:
                continue
            changed_q += 1
            entry["text"] = new_text
            if old_text != new_text:
                sub_map[old_text] = new_text
            # images（题后配图）：
            prev = entry.get("images")
            prev = [str(x) for x in prev] if isinstance(prev, list) else []
            inline_set = set(_BareToPaths(new_text, opts))
            kept = [p for p in prev if p not in inline_set]
            for p in moved:
                if p not in kept:
                    kept.append(p)
            entry["images"] = kept
            moved_q += len(moved)
        total_changed += changed_q
        total_moved += moved_q
        if sub_map:
            text_map[subject] = sub_map
        plans.append((path, subject, changed_q))
        _log(f"  · {subject}: 改 {changed_q} 道，移题后 {moved_q} 张")

    _log(f"  合计改动 {total_changed} 道题，移入题后 {total_moved} 张图")
    if dry_run:
        _log("\n  试运行结束。确认后运行： python migrate_inline_images.py")
        return 0

    stamp = _ts()
    backup_dir = os.path.join(BACKUPS_DIR, f"inline_img_v3_{stamp}")
    os.makedirs(backup_dir, exist_ok=True)
    for path, subject, _n in plans:
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
    for name in ("wrong_book.json", "brush_progress.json"):
        src = os.path.join(DATA_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, name))
    with open(os.path.join(backup_dir, "text_map.json"), "w", encoding="utf-8") as f:
        json.dump(text_map, f, ensure_ascii=False, indent=2)
    _log(f"\n  ✓ 备份到 backups/inline_img_v3_{stamp}/")

    for path, subject, _n in plans:
        data = _load(path, None)
        if not isinstance(data, list):
            continue
        # 直接按上面同样的规则改写（简单起见重跑一次转换写回）
        for entry in data:
            old_text = entry.get("text", "")
            new_text, moved, inline = convert_text(old_text)
            opts = entry.get("options")
            opts_changed = False
            if isinstance(opts, list):
                for o in opts:
                    if isinstance(o, (list, tuple)) and len(o) >= 2:
                        nt = convert_option(str(o[1]))
                        if nt != o[1]:
                            o[1] = nt
                            opts_changed = True
            if new_text == old_text and not moved and not inline and not opts_changed:
                continue
            entry["text"] = new_text
            prev = entry.get("images")
            prev = [str(x) for x in prev] if isinstance(prev, list) else []
            inline_set = set(_BareToPaths(new_text, opts))
            kept = [p for p in prev if p not in inline_set]
            for p in moved:
                if p not in kept:
                    kept.append(p)
            entry["images"] = kept
        _write(path, data)
    _log("  ✓ 题库文件已写入")

    _remap_personal(text_map)
    _log("\n  完成。建议执行：")
    _log("    python sync_bank.py build-manifest")
    _log("    git add data data_manifest.json")
    return 0


def _BareToPaths(text, opts):
    """收集新文本与选项中的图片路径（方括号与裸均可）"""
    from models.question import collect_image_tokens
    out = []
    if text:
        out = collect_image_tokens(text)
    if isinstance(opts, list):
        for o in opts:
            t = o[1] if isinstance(o, (list, tuple)) and len(o) >= 2 else (o if isinstance(o, str) else None)
            if t:
                out = list(dict.fromkeys(out + collect_image_tokens(t)))
    return out


def _remap_personal(text_map):
    for name in ("wrong_book.json", "brush_progress.json"):
        p = os.path.join(DATA_DIR, name)
        if name.endswith("wrong_book.json"):
            obj = _load(p, [])
            if isinstance(obj, list) and obj:
                changed = 0
                for rec in obj:
                    subj = rec.get("subject", "")
                    old = rec.get("question_text", "")
                    if subj in text_map and old in text_map[subj]:
                        rec["question_text"] = text_map[subj][old]
                        changed += 1
                if changed:
                    _write(p, obj)
                    _log(f"    {name}: 更新 {changed} 条")
        else:
            obj = _load(p, None)
            if isinstance(obj, dict) and isinstance(obj.get("remaining"), list):
                changed = 0
                for item in obj["remaining"]:
                    subj = item.get("subject", "")
                    old = item.get("text", "")
                    if subj in text_map and old in text_map[subj]:
                        item["text"] = text_map[subj][old]
                        changed += 1
                if changed:
                    _write(p, obj)
                    _log(f"    {name}: 更新 {changed} 条")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(run(dry_run="--dry-run" in sys.argv))
