# -*- coding: utf-8 -*-
"""
模拟考试记录（exams.json）
==========================
- 按 (owner, 科目) 记录：已考题目集合 examined_keys 与成绩历史 scores。
- examined_keys 用“题目稳定签名”标记（type/text/answer/options），不随题目序号变化。
- 通过率计算：最近至多 10 次成绩平均（不足用 0 补足到 10）。
账号功能预留：owner 默认 "default"。
"""

import datetime
import json
import os
import re

EXAMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exams.json")
DEFAULT_OWNER = "default"
MAX_SCORES = 50

_BLANK_KEY_RE = re.compile(r"【\s*\d+\s*】")  # 填空空位占位，参与签名时统一为 #


def _option_key(q) -> list:
    """选项文本按排序拼接：选项顺序/编号变化不影响“是否已考”判定"""
    opts = getattr(q, "options", None) or []
    norm = [re.sub(r"\s+", " ", str(txt or "")).strip() for _, txt in opts]
    return sorted(n for n in norm if n)


def question_key(q) -> str:
    """题目稳定签名（v2）：类型 + 规范化题干 + 可读答案 + 规范化选项"""
    text = _BLANK_KEY_RE.sub("#", q.text or "")
    parts = [q.get_type_name(), text, q.answer_text(), _option_key(q)]
    return json.dumps(parts, ensure_ascii=False, sort_keys=True)


def _load():
    if not os.path.exists(EXAMS_FILE):
        return {"users": {}}
    try:
        with open(EXAMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("users"), dict):
            return data
    except (ValueError, OSError):
        pass
    return {"users": {}}


def _save(data):
    with open(EXAMS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)



def mark_examined(owner: str, subject: str, keys: list):
    """把本次考试纳入考过集合（开考即计）"""
    owner = owner or DEFAULT_OWNER
    data = _load()
    rec = data["users"].setdefault(owner, {}).setdefault(subject, {"examined_keys": [], "scores": []})
    existing = set(rec.get("examined_keys") or [])
    existing.update(k for k in keys if k)
    rec["examined_keys"] = sorted(existing)
    _save(data)


def get_examined(owner: str, subject: str) -> set:
    owner = owner or DEFAULT_OWNER
    data = _load()
    rec = data["users"].get(owner, {}).get(subject, {})
    return set(rec.get("examined_keys") or [])


def save_score(owner: str, subject: str, score: float) -> list:
    """追加一次成绩，返回该科成绩列表"""
    owner = owner or DEFAULT_OWNER
    data = _load()
    rec = data["users"].setdefault(owner, {}).setdefault(subject, {"examined_keys": [], "scores": []})
    scores = rec.setdefault("scores", [])
    scores.append({"date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "score": round(float(score), 1)})
    if len(scores) > MAX_SCORES:
        del scores[:len(scores) - MAX_SCORES]
    _save(data)
    return scores


def get_scores(owner: str, subject: str) -> list:
    owner = owner or DEFAULT_OWNER
    data = _load()
    rec = data["users"].get(owner, {}).get(subject, {})
    return list(rec.get("scores") or [])


def avg_last10(owner: str, subject: str) -> float:
    """最近至多10次平均（0-100），不足10次按0补足到10再平均；0次=0"""
    scores = get_scores(owner, subject)[-10:]
    vals = [float(s.get("score", 0)) for s in scores]
    vals += [0.0] * (10 - len(vals))  # 补零到 10 个
    return sum(vals) / 10.0


def recent_exam_count(owner: str, subject: str) -> int:
    return len(get_scores(owner, subject))
