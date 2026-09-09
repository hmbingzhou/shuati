# -*- coding: utf-8 -*-
"""
图片按科目归类 + 题目↔图片一一对应整理工具
============================================
现状：pictures/ 扁平存放题目图片，题干/选项里用短文件名 token（如 1.png）引用。
目标：把图片移入 pictures/<科目>/（共用图放 _shared/，无人引用的放 _unused/），
      并把题目文本里的引用重写为带目录前缀的相对路径（数据结构/3.png）。

同时修复历史数据问题：
- 选项里 “A.5a.png” 这类“字母前缀混进文件名”的引用 → 自动去掉前缀引用真实文件；
- 磁盘缺失的图片保留引用并列入报告（等你把文件放入对应目录即可恢复）。

用法（项目根目录）：
    python reorganize_pictures.py --dry-run   # 只报告，不改任何文件
    python reorganize_pictures.py             # 备份 → 搬移 → 重写引用 → 报告
    python reorganize_pictures.py --check     # 完整性检查（不修改）
"""

import datetime
import json
import os
import re
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PICTURES_DIR = os.path.join(BASE_DIR, "pictures")
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")

USER_DATA_FILES = {"records.json", "wrong_book.json", "recycle_bin.json",
                   "exams.json", "brush_progress.json"}

IMG_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_\u4e00-\u9fff./-]+\.(?:png|jpe?g|gif|bmp|webp)", re.IGNORECASE)
# “字母 + 分隔符 + 真实文件名”的历史错误写法（如 A.5a.png）
_LABEL_PREFIX_RE = re.compile(r"^[A-Za-z][.．、]?(?=[\w\u4e00-\u9fff./-]+\.(?:png|jpe?g|gif|bmp|webp)$)")


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
            if not name.lower().endswith(".json") or name in USER_DATA_FILES:
                continue
            if name.startswith("."):
                continue
            out.append(os.path.join(DATA_DIR, name))
    return out


# ---------------------------------------------------------------- 引用收集 ----------------------------------------------------------------

def _field_texts(entry):
    """返回需要扫描/重写的文本字段（题干 + 各选项文本）"""
    texts = [str(entry.get("text") or "")]
    opts = entry.get("options")
    if isinstance(opts, list):
        for o in opts:
            if isinstance(o, (list, tuple)) and len(o) >= 2:
                texts.append(str(o[1]))
            elif isinstance(o, str):
                texts.append(o)
    return texts


def repair_token(token):
    """去掉历史“A.5a.png”式前缀，若去前缀后是真实存在的文件则返回修复名；否则原样"""
    if os.path.isfile(os.path.join(PICTURES_DIR, token)):
        return token
    m = _LABEL_PREFIX_RE.match(token)
    if m:
        rest = token[m.end():]
        if rest and os.path.isfile(os.path.join(PICTURES_DIR, rest)):
            return rest
    return token


def _entry_tokens(entry):
    """该题所有 token（题干+选项文本中出现）去重"""
    seen, out = set(), []
    for t in _field_texts(entry):
        for m in IMG_TOKEN_RE.finditer(t):
            tok = m.group(0)
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
    return out


# ---------------------------------------------------------------- 分析 ----------------------------------------------------------------

def analyze():
    """
    扫描题库与 pictures/，返回：
      owners:     有效文件(修复后) -> 引用它的科目集合
      raw_tokens: 每个出现过的原始 token（含修复别名信息）
      disk:       pictures 根目录的图片文件（扁平层）
      per_subject:{科目: [题 index/文本...]?}
    """
    owners = {}
    raw_token_subjects = {}
    disk_root = {}
    if os.path.isdir(PICTURES_DIR):
        for name in sorted(os.listdir(PICTURES_DIR)):
            p = os.path.join(PICTURES_DIR, name)
            if os.path.isfile(p) and os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
                disk_root[name] = p

    for path in _subject_files():
        subject = os.path.splitext(os.path.basename(path))[0]
        data = _load(path, None)
        if not isinstance(data, list):
            continue
        for entry in data:
            for raw in _entry_tokens(entry):
                raw_token_subjects.setdefault(raw, set()).add(subject)
                eff = repair_token(raw)
                owners.setdefault(eff, set()).add(subject)
    return owners, raw_token_subjects, disk_root


def decide_dirs(owners, raw_token_subjects, disk_root):
    """
    返回：
      file_dir: 有效文件(repair 后) -> 目标子目录(subject / _shared / _unused)
      token_rel: 原始 token -> 新的相对引用（含目录），None 表示不需要改
      move_list: [(源扁平路径, 目标子目录)]（已存在的文件）
      missing:   [token(有效) ...] 被引用但磁盘缺失
    """
    file_dir, move_list, missing = {}, [], []
    for eff in sorted(owners):
        subs = owners[eff]
        if not os.path.isfile(os.path.join(PICTURES_DIR, eff)):
            missing.append(eff)  # 引用了但缺文件（也缺别名文件）
            continue
        if len(subs) == 1:
            file_dir[eff] = next(iter(subs))
        elif len(subs) > 1:
            file_dir[eff] = "_shared"
        else:
            file_dir[eff] = "_unused"
        if os.path.isfile(os.path.join(PICTURES_DIR, eff)) and eff in disk_root:
            move_list.append((disk_root[eff], file_dir[eff]))

    token_rel = {}
    for raw in sorted(raw_token_subjects):
        eff = repair_token(raw)
        d = file_dir.get(eff)
        if d is None:
            # 缺失文件：仍按归属给目录（单科=科目；否则 _shared），让以后放文件即可用
            subs = owners.get(eff) or raw_token_subjects.get(raw) or set()
            d = next(iter(subs)) if len(subs) == 1 else ("_shared" if len(subs) > 1 else "")
        if d == "_unused":
            token_rel[raw] = None
            continue
        base = eff if eff in file_dir or os.path.isfile(os.path.join(PICTURES_DIR, eff)) else raw
        rel = f"{d}/{base}" if d else base
        if rel != raw:
            token_rel[raw] = rel
        else:
            token_rel[raw] = None
    return file_dir, token_rel, move_list, missing


def _rewrite_field(field, token_rel):
    """把文本中的原始 token 替换成带目录的新引用"""
    changed = False

    def _repl(m):
        nonlocal changed
        tok = m.group(0)
        new = token_rel.get(tok)
        if new is None:
            return tok
        if new != tok:
            changed = True
        return new

    return IMG_TOKEN_RE.sub(_repl, field), changed


# ---------------------------------------------------------------- 执行 ----------------------------------------------------------------

def run(dry_run: bool = True):
    from models.question import collect_image_tokens  # noqa: E402

    _log("=" * 60)
    _log(" 图片按科目归类整理" + ("（试运行，不改文件）" if dry_run else ""))
    _log("=" * 60)

    owners, raw_token_subjects, disk_root = analyze()
    file_dir, token_rel, move_list, missing = decide_dirs(owners, raw_token_subjects, disk_root)

    subs_used = {next(iter(v)) if len(v) == 1 else "_shared" for v in owners.values()}
    _log(f"  有效图片 {len(owners)} 个；目录计划："
         + json.dumps({d: sum(1 for v in owners.values() if (next(iter(v)) if len(v) == 1 else '_shared') == d)
                       for d in sorted({next(iter(v)) if len(v) == 1 else '_shared' for v in owners.values()})},
                      ensure_ascii=False))
    _log(f"  需要搬移 {len(move_list)} 个文件")
    _log(f"  磁盘缺失(被引用) {len(missing)} 个: {missing}")
    _log(f"  需要重写引用 token 数: {sum(1 for v in token_rel.values() if v)}")

    # 逐题重写计划
    rewrites = 0
    text_map = {}
    for path in _subject_files():
        subject = os.path.splitext(os.path.basename(path))[0]
        data = _load(path, None)
        if not isinstance(data, list):
            continue
        sub_map = {}
        for entry in data:
            fields = _field_texts(entry)
            if not any(token_rel.get(tok) for t in fields for tok in (IMG_TOKEN_RE.findall(t) or [])):
                continue
            changed_any = False
            texts_new = []
            for t in fields:
                nt, changed = _rewrite_field(t, token_rel)
                texts_new.append(nt)
                changed_any = changed_any or changed
            if not changed_any:
                continue
            # 写回题干与选项
            old_text = entry.get("text", "")
            entry["text"] = texts_new[0]
            if old_text != entry["text"]:
                sub_map[old_text] = entry["text"]
            opts = entry.get("options")
            if isinstance(opts, list):
                k = 1
                for oi, o in enumerate(opts):
                    if isinstance(o, (list, tuple)) and len(o) >= 2 and k < len(texts_new):
                        o[1] = texts_new[k]
                        k += 1
                    elif isinstance(o, str) and k < len(texts_new):
                        opts[oi] = texts_new[k]
                        k += 1
            entry["images"] = list(dict.fromkeys(
                collect_image_tokens(*(texts_new or [""]))))
            rewrites += 1
        if sub_map:
            text_map[subject] = sub_map

    _log(f"  需要重写的题目数: {rewrites}")
    if dry_run:
        _log("\n  试运行结束。确认后运行： python reorganize_pictures.py")
        return 0

    # ---- 备份 ----
    stamp = _ts()
    backup_dir = os.path.join(BACKUPS_DIR, f"pictures_reorg_{stamp}")
    flat_dir = os.path.join(backup_dir, "pictures_flat")
    os.makedirs(flat_dir, exist_ok=True)
    for path in _subject_files():
        shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
    for name in ("wrong_book.json", "brush_progress.json"):
        src = os.path.join(DATA_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, name))
    for rel in sorted(token_rel):
        if token_rel[rel]:
            src = os.path.join(PICTURES_DIR, rel)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(flat_dir, os.path.basename(rel)))
    _log(f"\n  ✓ 已备份到 backups/pictures_reorg_{stamp}/")

    # ---- 物理搬移 ----
    done = {}
    for src, d in move_list:
        os.makedirs(os.path.join(PICTURES_DIR, d), exist_ok=True)
        name = os.path.basename(src)
        dst = os.path.join(PICTURES_DIR, d, name)
        if os.path.exists(dst) and os.path.abspath(dst) != os.path.abspath(src):
            # 目标已存在同名：不覆盖，原文件仍保留在根目录并列入报告
            done[name] = {"dest": d, "skipped": True}
            continue
        shutil.move(src, dst)
        done[name] = {"dest": d}
    _log(f"  ✓ 搬移 {len(done)} 个文件")
    # 补建目录（为缺失文件预留）
    for eff in missing:
        d = file_dir.get(eff)
        if not d:
            subs = owners.get(eff)
            d = next(iter(subs)) if subs and len(subs) == 1 else "_shared"
        if d:
            os.makedirs(os.path.join(PICTURES_DIR, d), exist_ok=True)
        _log(f"    · 缺失待补: {d}/{eff}" if d else f"    · 缺失无归属: {eff}")

    # ---- 写回题库 ----
    for path in _subject_files():
        subject = os.path.splitext(os.path.basename(path))[0]
        data = _load(path, None)
        if not isinstance(data, list):
            continue
        need_save = False
        for entry in data:
            texts_new = []
            changed_any = False
            for t in _field_texts(entry):
                nt, changed = _rewrite_field(t, token_rel)
                texts_new.append(nt)
                changed_any = changed_any or changed
            if not changed_any:
                continue
            need_save = True
            entry["text"] = texts_new[0]
            opts = entry.get("options")
            if isinstance(opts, list):
                k = 1
                for oi, o in enumerate(opts):
                    if isinstance(o, (list, tuple)) and len(o) >= 2 and k < len(texts_new):
                        o[1] = texts_new[k]
                        k += 1
                    elif isinstance(o, str) and k < len(texts_new):
                        opts[oi] = texts_new[k]
                        k += 1
            entry["images"] = list(dict.fromkeys(
                collect_image_tokens(*(texts_new or [""]))))
        if need_save:
            _write(path, data)
    _log("  ✓ 题库引用已重写")

    # ---- 个人数据重映射 ----
    _remap_personal(text_map)

    # ---- 报告 ----
    review = _format_review(owners, token_rel, missing, move_list, text_map)
    _write(os.path.join(backup_dir, "review.md"), review)
    _log(f"  ✓ 报告已写入 backups/pictures_reorg_{stamp}/review.md")

    _log("\n  整理完成。建议执行：")
    _log("    python sync_bank.py build-manifest   # 重新生成图片/题库清单")
    _log("    git add pictures data data_manifest.json")
    _log("    git commit && git push")
    return 0


def _format_review(owners, token_rel, missing, move_list, text_map):
    lines = ["# 图片按科目归类整理报告", ""]
    by_dir = {}
    for eff, subs in owners.items():
        d = next(iter(subs)) if len(subs) == 1 else ("_shared" if len(subs) > 1 else "_unused")
        by_dir.setdefault(d, []).append(eff)
    for d in sorted(by_dir):
        lines.append(f"## pictures/{d} （{len(by_dir[d])} 张）")
        for name in sorted(by_dir[d]):
            users = ",".join(sorted(owners[name]))
            lines.append(f"- {name}   [使用科目: {users}]")
    if missing:
        lines.append("")
        lines.append("## 被引用但磁盘缺失（请补图后放入对应目录）")
        for m in missing:
            lines.append(f"- {m}")
    lines.append("")
    lines.append("## 引用重写映射（旧 token → 新相对路径）")
    for raw, rel in sorted(token_rel.items()):
        if rel:
            lines.append(f"- {raw} → {rel}")
    lines.append("")
    if text_map:
        lines.append("## 题面文本变化（错题本/进度已按此映射）")
        for subj, m in text_map.items():
            lines.append(f"### {subj} ({len(m)} 道)")
            for old, new in m.items():
                lines.append(f"- 旧: {old[:60]}")
                lines.append(f"  新: {new[:60]}")
    return "\n".join(lines) + "\n"


def _remap_personal(text_map):
    wb_path = os.path.join(DATA_DIR, "wrong_book.json")
    wb = _load(wb_path, [])
    if isinstance(wb, list) and wb:
        changed = 0
        for rec in wb:
            subj = rec.get("subject", "")
            old = rec.get("question_text", "")
            if subj in text_map and old in text_map[subj]:
                rec["question_text"] = text_map[subj][old]
                changed += 1
        if changed:
            _write(wb_path, wb)
            _log(f"    wrong_book.json: 更新 {changed} 条文本引用")
    bp_path = os.path.join(DATA_DIR, "brush_progress.json")
    bp = _load(bp_path, None)
    if isinstance(bp, dict) and isinstance(bp.get("remaining"), list) and bp["remaining"]:
        changed = 0
        for item in bp["remaining"]:
            subj = item.get("subject", "")
            old = item.get("text", "")
            if subj in text_map and old in text_map[subj]:
                item["text"] = text_map[subj][old]
                changed += 1
        if changed:
            _write(bp_path, bp)
            _log(f"    brush_progress.json: 更新 {changed} 条文本引用")


def check():
    """完整性检查：每题引用的图片（带目录相对 pictures）都能找到；扁平层只允许空/_unused 等。"""
    from question_manager import load_questions
    from models.question import collect_image_tokens
    problems = []
    total_q = total_img = 0
    for f in _subject_files():
        subject = os.path.splitext(os.path.basename(f))[0]
        for q in load_questions(subject):
            total_q += 1
            extra = [t for _, t in (getattr(q, "options", None) or [])]
            toks = list(dict.fromkeys(collect_image_tokens(q.text or "", *extra)))
            total_img += len(toks)
            for tok in toks:
                p = os.path.join(PICTURES_DIR, tok.replace("/", os.sep))
                if not os.path.isfile(p):
                    problems.append((subject, tok))
    root_files = [n for n in os.listdir(PICTURES_DIR) if os.path.isfile(os.path.join(PICTURES_DIR, n))
                  and os.path.splitext(n)[1].lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}]
    print(f"检查 {total_q} 题 / {total_img} 处图片引用")
    if problems:
        print(f"⚠️ 缺失引用 {len(problems)} 处:")
        for s, tok in problems[:50]:
            print(f"  [{s}] {tok}")
    else:
        print("✔ 全部题目引用的图片都能在磁盘找到")
    print("扁平层残留图片文件:", root_files or "无 ✔")
    return 0 if not problems else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = sys.argv[1:]
    if "--check" in args:
        sys.exit(check())
    sys.exit(run(dry_run="--dry-run" in args))
