# -*- coding: utf-8 -*-
"""
分科目刷题记录（预留“属主/账号”分层）
=====================================
文件：data/records.json
结构：
  { users: { "<owner>": { "<科目>": { "<题型label>": {total, correct}, ... } } } }

- owner 默认 "default"。当前网页版全部记在 default；
  未来接入账号功能时，把 owner 换成对应用户标识即可，无需改动统计逻辑。
- 记录来源：网页版每次作答（含错题复习）；按题型（判断题/单选题/多选题/填空题/简答题）累计。
- 正确率 = correct / total（0..1），展示时转百分比。
"""

import datetime
import json
import os

RECORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "records.json")
DEFAULT_OWNER = "default"

_TYPE_LABELS = ("判断题", "单选题", "多选题", "填空题", "简答题")


def _load():
    if not os.path.exists(RECORDS_FILE):
        return {"users": {}}
    try:
        with open(RECORDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("users"), dict):
            return data
    except (ValueError, OSError):
        pass
    return {"users": {}}


def _save(data):
    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_result(owner: str, subject: str, type_label: str, correct: bool, occurred_at: str = None):
    """累计一条作答记录（owner 缺省为 default）"""
    owner = owner or DEFAULT_OWNER
    subject = (subject or "").strip()
    type_label = (type_label or "").strip()
    if not subject or not type_label:
        return
    data = _load()
    user_map = data["users"].setdefault(owner, {})
    subj = user_map.setdefault(subject, {})
    cell = subj.setdefault(type_label, {"total": 0, "correct": 0})
    cell["total"] = cell.get("total", 0) + 1
    if correct:
        cell["correct"] = cell.get("correct", 0) + 1
    _save(data)


def _empty_breakdown():
    return {"total": 0, "correct": 0, "wrong": 0, "accuracy": None,
            "types": [{"label": t, "total": 0, "correct": 0, "wrong": 0, "accuracy": None} for t in _TYPE_LABELS]}


def get_subject_breakdown(owner: str, subject: str) -> dict:
    """某属主某科目的按题型明细（含合计）"""
    owner = owner or DEFAULT_OWNER
    data = _load()
    subj = data["users"].get(owner, {}).get(subject, {})
    types = []
    for t in _TYPE_LABELS:
        cell = subj.get(t) or {}
        total = int(cell.get("total", 0) or 0)
        correct = int(cell.get("correct", 0) or 0)
        wrong = total - correct
        types.append({"label": t, "total": total, "correct": correct, "wrong": wrong,
                      "accuracy": round(correct / total * 100, 1) if total else None})
    return _compute({"types": types})


def _compute(breakdown):
    total = sum(t["total"] for t in breakdown["types"])
    correct = sum(t["correct"] for t in breakdown["types"])
    breakdown["total"] = total
    breakdown["correct"] = correct
    breakdown["wrong"] = total - correct
    breakdown["accuracy"] = round(correct / total * 100, 1) if total else None
    return breakdown


def get_overview_records(owner: str) -> dict:
    """某属主全部科目的记录（科目 -> 明细；无记录的科目不出现）"""
    owner = owner or DEFAULT_OWNER
    data = _load()
    out = {}
    for subject, subj in (data["users"].get(owner, {}) or {}).items():
        types = []
        for t in _TYPE_LABELS:
            cell = subj.get(t) or {}
            total = int(cell.get("total", 0) or 0)
            correct = int(cell.get("correct", 0) or 0)
            types.append({"label": t, "total": total, "correct": correct, "wrong": total - correct,
                          "accuracy": round(correct / total * 100, 1) if total else None})
        out[subject] = _compute({"types": types})
    return out


def list_owners() -> list:
    data = _load()
    return sorted(data["users"].keys())


def clear_owner(owner: str) -> int:
    """清空某属主全部记录，返回清除科目数"""
    owner = owner or DEFAULT_OWNER
    data = _load()
    removed = len(data["users"].pop(owner, {}))
    _save(data)
    return removed


def clear_all() -> int:
    data = _load()
    removed = sum(len(v) for v in data["users"].values())
    data["users"] = {}
    _save(data)
    return removed
