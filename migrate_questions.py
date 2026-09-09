# -*- coding: utf-8 -*-
"""
题库存储格式 v1 → v2 迁移工具
===============================
v1：type=选择题(choice_type/multiple_answers) / 填空题 answer 为整串字符串 / 图片内嵌文本
v2：六题型 type 独立；填空 answer={items:[{accept:[...], group?}]}；统一 images 字段

用法（项目根目录）:
    python migrate_questions.py --dry-run      # 只报告，不改文件
    python migrate_questions.py                # 先备份，再迁移 data/*.json 并重映射个人数据

流程：
1. 把所有 data/*.json（题库 + 个人数据文件）备份到 backups/migrate_v2_<时间戳>/
2. 逐科迁移：
   - 选择题按 choice_type 拆为 单选题/多选题（多选 answer 用字母串，丢弃 multiple_answers）
   - 图片 token 由模型 to_dict 收集进 images（文本不动）
   - 填空题：空位统一为 【N】 顺序编号；整串答案按空白拆分为每空 accept
   - 无法可靠拆分的题进入“待人工检查”清单
3. 以 (科目, 旧text)->新text 重映射 wrong_book.json / brush_progress.json
4. 逐文件回读校验（from_dict→to_dict 与写入内容一致），失败的文件不写入并报告
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

MARK_RE = re.compile(r"【\s*第?\s*(\d+)[^】]*】")
# （     ） / (     ) / （　　）等带空白（含全角空格）的括号组视为“未编号空位”
PAREN_RE = re.compile(r"[（(][\s\u3000]+[）)]")
# ≥2 个下划线，且两侧都不是 ascii 字母数字（避免误伤标识符）
UNDER_RE = re.compile(r"(?<![A-Za-z0-9])_{2,}(?![A-Za-z0-9])")


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


# ---------------------------------------------------------------- 填空迁移 ----------------------------------------------------------------

def _find_blank_spans(text):
    """返回 [(start, end, kind, number_or_None)]，按文本顺序"""
    spans = []
    for m in MARK_RE.finditer(text):
        spans.append((m.start(), m.end(), "mark", int(m.group(1))))
    for m in PAREN_RE.finditer(text):
        spans.append((m.start(), m.end(), "paren", None))
    for m in UNDER_RE.finditer(text):
        spans.append((m.start(), m.end(), "under", None))
    spans.sort(key=lambda s: (s[0], s[1]))
    return spans


def canonicalize_fill_text(text):
    """
    把全部空位统一改写为 【1】【2】…（按文本顺序编号）。
    若原文已正是这种规范形式则保持不变。
    返回 (新文本, 是否变化)
    """
    spans = _find_blank_spans(text)
    if not spans:
        return text, False
    out, j, pos = [], 0, 0
    for (s, e, _kind, _num) in spans:
        out.append(text[pos:s])
        j += 1
        out.append(f"【{j}】")
        pos = e
    out.append(text[pos:])
    joined = "".join(out)
    return (text if joined == text else joined), joined != text


def migrate_fill_question(q: dict):
    """
    迁移一道填空题：返回 (新dict, review_reason|None)
    - 题干空位能按编号与答案空白分词一一对应 → 标准逐空 answer
    - 否则降级为「整串答案」(whole=True)，语义与 v1 一致，进人工清单核对
    """
    text = q.get("text", "")
    ans = str(q.get("answer") or "").strip()
    tokens = re.split(r"\s+", ans) if ans else []
    n = len(_find_blank_spans(text))

    def _whole(reason):
        return {**dict(q), "type": "填空题", "text": text,
                "answer": {"whole": True, "items": [{"accept": [ans]}] if ans else []},
                "choice_type": None, "multiple_answers": None}, reason

    q = dict(q)
    q.pop("choice_type", None)
    q.pop("multiple_answers", None)

    if n == 0:
        # 题干没有任何可识别的空位标记（例如“写出运行结果”类整串题）
        return _whole("题干没有空位标记，按整串答案处理，请确认题型")
    if len(tokens) != n:
        return _whole(f"答案分词 {len(tokens)} 个 ≠ 空位数 {n}，按整串答案处理，请核对")

    new_text, _changed = canonicalize_fill_text(text)
    items = [{"accept": [t]} for t in tokens]
    q["type"] = "填空题"
    q["text"] = new_text
    q["answer"] = {"items": items}
    return q, None


def migrate_question(q: dict):
    """返回 (新dict, review_reason|None)"""
    t = q.get("type")
    if t == "选择题":
        nq = dict(q)
        multiple = str(q.get("choice_type", "single")).lower() == "multiple"
        answer = str(q.get("answer") or "").strip()
        if not answer and q.get("multiple_answers"):
            answer = "".join(str(x) for x in q["multiple_answers"])
        nq["type"] = "多选题" if multiple else "单选题"
        nq["answer"] = answer
        nq.pop("choice_type", None)
        nq.pop("multiple_answers", None)
        return nq, None
    if t == "填空题":
        return migrate_fill_question(q)
    nq = dict(q)
    for k in ("choice_type", "multiple_answers"):
        nq.pop(k, None)
    return nq, None


def _subject_files():
    out = []
    if not os.path.isdir(DATA_DIR):
        return out
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.lower().endswith(".json") or name in USER_DATA_FILES:
            continue
        if name.startswith("."):
            continue
        out.append(os.path.join(DATA_DIR, name))
    return out


# ---------------------------------------------------------------- 主流程 ----------------------------------------------------------------

def run(dry_run: bool = True):
    from models.question import Question  # 延迟导入，便于单独调试

    _log("=" * 60)
    _log(" 题库存储格式 v1 → v2 迁移" + ("（试运行，不会改文件）" if dry_run else ""))
    _log("=" * 60)

    plans = []       # {path, subject, old_list, new_list, text_map, problems}
    review_all = []
    type_stats = {}
    total_old = total_new = 0

    for path in _subject_files():
        subject = os.path.splitext(os.path.basename(path))[0]
        old_list = _load(path, None)
        if not isinstance(old_list, list):
            _log(f"  ⚠️ {subject}: 跳过（不是列表）")
            continue
        new_list, sub_map = [], {}
        for q in old_list:
            nq, review = migrate_question(q)
            new_list.append(nq)
            if review:
                review_all.append({"subject": subject, "review": review,
                                   "text": (nq.get("text") or "")[:90]})
            if (q.get("text") or "") != (nq.get("text") or ""):
                sub_map[q.get("text", "")] = nq.get("text", "")
        for nq in new_list:
            type_stats[nq.get("type", "?")] = type_stats.get(nq.get("type", "?"), 0) + 1
        problems = _validate_roundtrip(new_list, subject)
        plans.append({"path": path, "subject": subject, "old_list": old_list,
                      "new_list": new_list, "text_map": sub_map, "problems": problems})
        total_old += len(old_list)
        total_new += len(new_list)
        tag = "✓ 校验通过" if not problems else f"✗ 往返校验 {len(problems)} 条(将跳过)"
        _log(f"  · {subject}: {len(old_list)} → {len(new_list)} 题，文本重编号 {len(sub_map)} 道  {tag}")

    _log("-" * 60)
    _log(f"  合计: {total_old} 题 → {total_new} 题")
    _log("  迁移后题型分布: " + json.dumps(type_stats, ensure_ascii=False))
    if review_all:
        _log(f"  ⚠️ 待人工检查 {len(review_all)} 道填空：")
        for r in review_all[:20]:
            _log(f"    · [{r['subject']}] {r['review']} | {r['text']}")
        if len(review_all) > 20:
            _log(f"    … 其余 {len(review_all) - 20} 条见报告文件")
    else:
        _log("  ✓ 无待人工检查的题目")

    if dry_run:
        _log("\n  试运行结束。确认无误后运行： python migrate_questions.py")
        return 0

    # ---- 先备份（迁移前的原始文件）----
    stamp = _ts()
    backup_dir = os.path.join(BACKUPS_DIR, f"migrate_v2_{stamp}")
    os.makedirs(backup_dir, exist_ok=True)
    for p in plans:
        shutil.copy2(p["path"], os.path.join(backup_dir, os.path.basename(p["path"])))
    for name in USER_DATA_FILES:
        src = os.path.join(DATA_DIR, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, name))
    text_map = {p["subject"]: p["text_map"] for p in plans if p["text_map"]}
    _write(os.path.join(backup_dir, "review.md"), _format_review(review_all, text_map))
    _write(os.path.join(backup_dir, "text_map.json"),
           {s: m for s, m in text_map.items()})
    _log(f"\n  ✓ 原始文件已备份到 backups/migrate_v2_{stamp}/")

    # ---- 写入 v2 ----
    for p in plans:
        if p["problems"]:
            _log(f"  ⚠️ {p['subject']}: 校验失败，跳过写入")
            continue
        _write(p["path"], p["new_list"])
    _log("  ✓ 题库文件已写入 v2 格式")

    # ---- 重映射个人数据（错题本/进度）----
    _remap_personal(text_map)
    _log("  ✓ wrong_book.json / brush_progress.json 已按文本映射更新")

    _log("\n  迁移完成。建议执行：")
    _log("    python sync_bank.py build-manifest   # 重新生成题库同步清单")
    _log("    git add data data_manifest.json pictures")
    _log("    git commit -m '题库迁移到 v2 存储格式' && git push")
    return 0


def _validate_roundtrip(new_list, subject):
    """from_dict -> to_dict 与写入内容一致（逐关键字段比较）"""
    from models.question import Question
    problems = []
    for i, nq in enumerate(new_list):
        try:
            d2 = Question.from_dict(nq).to_dict()
            for key in ("type", "text", "subject", "answer"):
                if d2.get(key) != nq.get(key):
                    problems.append((i, key, nq.get(key), d2.get(key)))
                    break
        except Exception as e:  # noqa: BLE001
            problems.append((i, "exception", str(e), ""))
            break
    return problems


def _format_review(review_all, text_map):
    lines = ["# v2 迁移·待人工检查清单", ""]
    if review_all:
        for r in review_all:
            lines.append(f"- [{r['subject']}] {r['review']}")
            lines.append(f"  题干: {r['text']}")
    else:
        lines.append("无。")
    lines.append("")
    lines.append("## 文本重编号的题（旧 text → 新 text）")
    if text_map:
        for subj, m in text_map.items():
            lines.append(f"### {subj} ({len(m)} 道)")
            for old, new in m.items():
                lines.append(f"- 旧: {old[:60]}")
                lines.append(f"  新: {new[:60]}")
    else:
        lines.append("无。")
    return "\n".join(lines) + "\n"


def _remap_personal(text_map):
    """重映射 wrong_book.json / brush_progress.json 中引用旧文本的条目"""
    wb_path = os.path.join(DATA_DIR, "wrong_book.json")
    wb = _load(wb_path, [])
    if isinstance(wb, list) and wb:
        changed = 0
        for rec in wb:
            subj = rec.get("subject", "")
            old_text = rec.get("question_text", "")
            if subj in text_map and old_text in text_map[subj]:
                rec["question_text"] = text_map[subj][old_text]
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
            old_text = item.get("text", "")
            if subj in text_map and old_text in text_map[subj]:
                item["text"] = text_map[subj][old_text]
                changed += 1
        if changed:
            _write(bp_path, bp)
            _log(f"    brush_progress.json: 更新 {changed} 条文本引用")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(run(dry_run="--dry-run" in sys.argv))
