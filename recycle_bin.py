# -*- coding: utf-8 -*-
"""
回收站模块（data/recycle_bin.json）
==================================
- 容量上限：最多 500 条；超限自动丢弃最旧的记录。
- 每条记录：{id, subject, original_index, deleted_at, item:{...题库原始 JSON 题...}}
- add: 写入删除的题目；restore: 按原序号尽量插回题库并移除记录；
  purge/purge_all: 彻底删除。
"""

import datetime
import json
import os

from models.question import Question
from question_manager import load_questions, save_questions

RECYCLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "recycle_bin.json")
MAX_ITEMS = 500


def _load():
    if not os.path.exists(RECYCLE_FILE):
        return []
    try:
        with open(RECYCLE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _save(records):
    with open(RECYCLE_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def add(items):
    """items: [{subject, original_index, item:{题库JSON题}}...]
    追加记录，并把总条数裁剪到 MAX_ITEMS（丢最旧）。返回当前条数。"""
    records = _load()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for it in items:
        records.append({
            "id": 0,  # 下面统一重排
            "subject": it["subject"],
            "original_index": it.get("original_index", 0),
            "deleted_at": now,
            "item": it["item"],
        })
    # 统一规整 id（1..n），保证不重复
    for idx, rec in enumerate(records):
        rec["id"] = idx + 1

    if len(records) > MAX_ITEMS:
        records = records[-MAX_ITEMS:]
    _save(records)
    return len(records)


def list_records(subject=None):
    """返回记录（最新在前）；subject 可过滤"""
    records = _load()
    if subject and subject not in ("", "全部", "全部科目", "所有科目"):
        records = [r for r in records if r.get("subject") == subject]
    return list(reversed(records))


def _bank_insert(subject, original_index, item):
    """把题目尽量插回原位置，返回是否成功"""
    bank = load_questions(subject)
    try:
        q = Question.from_dict(item)
    except Exception:
        return False
    q.subject = subject
    pos = original_index if original_index <= len(bank) else len(bank)
    if pos < 0:
        pos = len(bank)
    bank.insert(pos, q)
    save_questions(subject, bank)
    return True


def restore(ids):
    """按 id 恢复（尽量回原位置）。返回 (restored, missing_ids)"""
    if not ids:
        return (0, [])
    records = _load()
    want = set(ids)
    restored = 0
    missing = []
    remain = []
    for rec in records:
        rid = rec.get("id")
        if rid in want:
            ok = _bank_insert(rec.get("subject", ""), rec.get("original_index", 0), rec.get("item", {}))
            if ok:
                restored += 1
            else:
                missing.append(rid)  # 无法反序列化的题仍保留在回收站由用户处理
                remain.append(rec)
                continue
        else:
            remain.append(rec)
    _save(remain)
    return (restored, missing)


def purge(ids=None):
    """彻底删除指定记录；ids=None 表示清空全部。返回删除条数"""
    records = _load()
    if ids is None:
        n = len(records)
        _save([])
        return n
    want = set(ids)
    remain = [r for r in records if r.get("id") not in want]
    n = len(records) - len(remain)
    _save(remain)
    return n


def purge_all():
    return purge(None)
