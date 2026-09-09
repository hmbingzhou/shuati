# -*- coding: utf-8 -*-
"""
题库查重（相似题检测）
=====================
- normalize_text(): 文本归一化（去格式噪音）
- similarity_percent(): 题干字符级序列相似度百分比（difflib.SequenceMatcher）
- find_duplicates(): 在科目内【同题型】两两比较相似题，按相似度降序返回

相似度方法说明：
1) 按题型分组：判断题/单选题/多选题/填空题/简答题各自内部比对，跨题型不比。
2) 题干归一化：统一换行并把连续空白压成单个空格；去掉开头题号与空白占位括号。
3) ratio = 2 * M / (len(A)+len(B))，M 为归一化文本间所有最长匹配块的
   匹配字符总数；百分比 = round(ratio*100)。100% 表示归一化后完全相同。
4) 选择题（单选/多选）查重含选项：
   - 每个选项文本归一化后排序拼接成规范串 => 选项换顺序不影响比对；
   - 选择题相似度 = 题干相似度 × 60% + 选项相似度 × 40%；
     同题干 + 同选项（仅顺序不同）→ 100%。
   判断题/填空题/简答题只用题干文本相似度。
不识别语义同义改写。
"""

import difflib
import re

from models.question import ChoiceQuestion
from question_manager import load_questions

CHOICE_LABELS = ("单选题", "多选题")
STEM_WEIGHT = 60
OPT_WEIGHT = 40


def normalize_text(text: str) -> str:
    """题干归一化：去掉不影响题意的格式噪音"""
    t = str(text or "")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\s+", " ", t).strip()          # 连续空白 -> 单个空格
    t = re.sub(r"^\d+[lL]?[．、.，,：:]\s*", "", t)  # 去掉开头题号
    t = re.sub(r"[（(]\s*[）)]", "", t)          # 去掉空白占位括号 ( ) （ ）
    return t


def similarity_percent(a: str, b: str) -> int:
    """两条题干的相似度百分比（0..100）"""
    na, nb = normalize_text(a), normalize_text(b)
    return round(difflib.SequenceMatcher(None, na, nb).ratio() * 100)


def _option_key(q) -> str:
    """选择题选项规范串：各选项归一化后排序拼接 => 换顺序不影响"""
    if not isinstance(q, ChoiceQuestion) or not q.options:
        return ""
    normalized = sorted(normalize_text(txt) for _, txt in q.options if txt)
    return "\u0001".join(normalized)


def _label(q) -> str:
    if isinstance(q, ChoiceQuestion):
        return "多选题" if q.choice_type == "multiple" else "单选题"
    return q.get_type_label()


def _pair_similarity(qa, qb) -> int:
    """同组两题相似度：选择题 = 题干×60% + 选项×40%；其余 = 题干相似度
    仅用于同题型内部；跨题型直接返回 0。"""
    if _label(qa) != _label(qb):
        return 0
    is_choice = isinstance(qa, ChoiceQuestion) and isinstance(qb, ChoiceQuestion)
    stem = difflib.SequenceMatcher(None, normalize_text(qa.text), normalize_text(qb.text)).ratio()
    if not is_choice:
        return round(stem * 100)
    oa = _option_key(qa)
    ob = _option_key(qb)
    opt = difflib.SequenceMatcher(None, oa, ob).ratio() if (oa or ob) else 1.0
    return round(stem * STEM_WEIGHT + opt * OPT_WEIGHT)


def _preview(text: str, max_len: int = 60) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t[:max_len] + ("..." if len(t) > max_len else "")


def _item(q, index: int) -> dict:
    return {
        "index": index,
        "label": _label(q),
        "type": q.get_type_name(),
        "text": q.text,
        "answer": q.answer,
        "options": q.to_dict().get("options"),
        "choice_type": getattr(q, "choice_type", None),
        "preview": _preview(q.text),
    }


def find_duplicates(subject: str, threshold: int = 60, top: int = 300, progress_cb=None):
    """
    在指定科目内两两比较题干相似度，返回降序排列的题对。

    Args:
        subject: 科目名
        threshold: 相似度阈值百分比（含），默认 60
        top: 最多返回的题对数（超出置 truncated=True）
        progress_cb: 可选回调 progress_cb(percent:int 0..100)，用于后台任务上报进度
    Returns:
        {subject, total, threshold, pairs:[{a:item, b:item, similarity}], truncated}
    """
    questions = load_questions(subject)
    result = {
        "subject": subject,
        "total": len(questions),
        "threshold": threshold,
        "pairs": [],
        "truncated": False,
    }
    if len(questions) < 2:
        if progress_cb:
            progress_cb(100)
        return result

    norm = [normalize_text(q.text) for q in questions]
    lens = [len(n) for n in norm]
    labels = [_label(q) for q in questions]
    matches = []

    # 仅统计同题型内部的比较对数（跨题型不比），用于进度估算
    from collections import Counter
    group_count = Counter(labels)
    total_pairs = sum(c * (c - 1) // 2 for c in group_count.values())
    throttle = max(1, total_pairs // 200)
    done = 0
    last_pct = -1

    def _report(pct):
        nonlocal last_pct
        if progress_cb and pct > last_pct:
            last_pct = pct
            progress_cb(min(99, pct))

    n = len(questions)
    for i in range(n):
        for j in range(i + 1, n):
            if labels[i] != labels[j]:
                continue  # 跨题型不比
            done += 1
            if total_pairs and done % throttle == 0:
                _report(round(done * 100 / total_pairs))
            if lens[i] == 0 or lens[j] == 0:
                continue
            # 长度上限剪枝：题干部分 similarity 不可能超过 2*min/(lenA+lenB)
            stem_upper = 2 * min(lens[i], lens[j]) / (lens[i] + lens[j])
            if labels[i] in CHOICE_LABELS:
                # 选择题还有选项分量（上限 0.4），理论上限更高
                upper = stem_upper * STEM_WEIGHT / 100 + OPT_WEIGHT / 100
            else:
                upper = stem_upper
            if upper * 100 < threshold:
                continue
            sim = _pair_similarity(questions[i], questions[j])
            if sim < threshold:
                continue
            matches.append((sim, i, j))

    if progress_cb:
        progress_cb(100)

    matches.sort(key=lambda m: (-m[0], m[1], m[2]))
    pairs = []
    for sim, i, j in matches[:top]:
        pairs.append({
            "similarity": sim,
            "a": _item(questions[i], i),
            "b": _item(questions[j], j),
        })
    result["pairs"] = pairs
    result["truncated"] = len(matches) > top
    return result


if __name__ == "__main__":
    import sys

    _subject = sys.argv[1] if len(sys.argv) > 1 else "Java"
    _threshold = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    r = find_duplicates(_subject, _threshold)
    print(f"科目 {_subject} 共 {r['total']} 题，相似度 ≥ {_threshold}% 的有 {len(r['pairs'])} 对")
    for p in r["pairs"][:20]:
        print(f"  {p['similarity']:3d}%  #{p['a']['index']} {p['a']['preview'][:24]}...  <->  #{p['b']['index']} {p['b']['preview'][:24]}...")
