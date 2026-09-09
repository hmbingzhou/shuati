# -*- coding: utf-8 -*-
"""
刷题软件 - 网页版后端服务
=========================
纯 Python 标准库实现（http.server），无第三方依赖。

- 复用项目已有的 models / question_manager / utils，保证与终端版数据格式完全一致。
- 提供 JSON REST API，供 webui/ 目录下的前端页面调用。
- 同时托管静态页面（webui/index.html 等）与题目图片（pictures/ 目录）。

启动方式（在项目根目录）:
    python webui_server.py            # 默认 http://127.0.0.1:8000
    python webui_server.py --port 9000
    python webui_server.py --no-browser

也可通过 launcher.py 选择「网页版」启动。
"""

import datetime
import json
import mimetypes
import os
import re
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- 路径 ----------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEBUI_DIR = os.path.join(BASE_DIR, "webui")
PICTURES_DIR = os.path.join(BASE_DIR, "pictures")
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# 允许在页面展示的图片扩展名
_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}

# ---------------------------------------------------------------- 复用核心模块 ----------------------------------------------------------------

sys.path.insert(0, BASE_DIR)

# judge 转换插件目录（convert_tools/），供批量导入接口使用
CONVERT_TOOLS_DIR = os.path.join(BASE_DIR, "convert_tools")
if CONVERT_TOOLS_DIR not in sys.path:
    sys.path.insert(0, CONVERT_TOOLS_DIR)

from models.question import (  # noqa: E402
    Question,
    ChoiceQuestion,
    QuestionFactory,
)
from question_manager import (  # noqa: E402
    load_questions,
    save_questions,
    load_wrong_records,
    save_wrong_records,
    add_wrong_record,
    remove_wrong_record,
    update_wrong_record_timestamp,
    save_brush_progress,
    load_brush_progress,
    clear_brush_progress,
    has_brush_progress,
)
from utils.helpers import get_subject_list, GRADE_SUBJECTS, GRADE_ORDER  # noqa: E402
from duplicate_finder import find_duplicates as _find_duplicates  # noqa: E402
import recycle_bin  # noqa: E402
import records  # noqa: E402
import exams  # noqa: E402
import exam_config  # noqa: E402
import random as _random  # noqa: E402
import archive_manager  # noqa: E402
import sync_bank  # noqa: E402


# ---------------------------------------------------------------- 工具函数 ----------------------------------------------------------------

def _question_label(q: Question) -> str:
    """题型的显示标签：单选/多选分开，与 models 中 get_type_label 一致"""
    if isinstance(q, ChoiceQuestion):
        return "多选题" if q.choice_type == "multiple" else "单选题"
    return q.get_type_label()


def _q_to_item(q: Question, subject: str, index: int) -> dict:
    """把 Question 对象转成前端友好的 JSON（含 index、显示标签、可读答案与题型信息）"""
    d = q.to_dict()
    d["subject"] = subject
    d["index"] = index
    d["label"] = _question_label(q)
    d["options"] = d.get("options")
    d["flag_star"] = bool(q.flag_star)
    d["flag_cross"] = bool(q.flag_cross)
    # v2 附加信息
    d["answerText"] = q.answer_text()
    d["autoGraded"] = bool(q.is_auto_graded())
    d["blankCount"] = getattr(q, "blank_count", lambda: None)() if hasattr(q, "whole_string") else None
    d["wholeString"] = bool(getattr(q, "whole_string", False))
    d["choiceType"] = getattr(q, "choice_type", None)  # 兼容旧前端
    return d


def _load_subject_items(subject: str):
    """返回 (questions列表, items列表)"""
    questions = load_questions(subject)
    items = [_q_to_item(q, subject, i) for i, q in enumerate(questions)]
    return questions, items


def _match_label(q: Question, label: str) -> bool:
    """按展示标签过滤：单选题/多选题是选择题的两个子类"""
    if label == "选择题":
        return isinstance(q, ChoiceQuestion)
    return _question_label(q) == label


# ---------------------------------------------------------------- REST 处理 ----------------------------------------------------------------

def handle_overview(query=None):
    """仪表盘数据：年级分组科目、题数、错题数、进度、答题正确率记录"""
    owner = (query.get("owner", [records.DEFAULT_OWNER])[0] if query else records.DEFAULT_OWNER)
    rec_map = records.get_overview_records(owner)
    subjects = get_subject_list()
    questions_map = {s: _load_subject_items(s)[0] for s in subjects}
    wrong_records = load_wrong_records()
    wrong_count_map = {}
    for r in wrong_records:
        wrong_count_map[r.subject] = wrong_count_map.get(r.subject, 0) + 1

    def _empty_subj_records():
        return {"total": 0, "correct": 0, "wrong": 0, "accuracy": None, "types": []}

    total_q = 0
    grades = []
    for grade in GRADE_ORDER:
        gsubs = []
        for subj in GRADE_SUBJECTS.get(grade, []):
            qs = questions_map.get(subj, [])
            total_q += len(qs)
            rec = rec_map.get(subj, _empty_subj_records())
            gsubs.append({
                "name": subj,
                "questionCount": len(qs),
                "wrongCount": wrong_count_map.get(subj, 0),
                "records": rec,
                "exam": _exam_block(owner, subj, rec),
            })
        if gsubs:
            grades.append({"name": grade, "subjects": gsubs})

    total_wrong = len(wrong_records)
    return {
        "grades": grades,
        "totalQuestions": total_q,
        "totalWrong": total_wrong,
        "hasProgress": has_brush_progress(),
        "progress": _load_progress_summary(),
    }


def _load_progress_summary():
    """进度概要（不含完整剩余列表，供首页展示）"""
    p = load_brush_progress()
    if not p:
        return None
    remaining = p.get("remaining", [])
    return {
        "subject": p.get("subject", ""),
        "mode": p.get("mode", ""),
        "type_label": p.get("type_label"),
        "total": p.get("total", 0),
        "remainingCount": len(remaining),
    }


def handle_questions(query):
    """
    题目列表/搜索
    参数: subject(空=全部科目)  keyword  type/label  flags(star|cross|any)  page  pageSize
    """
    subject = query.get("subject", [""])[0]
    keyword = query.get("keyword", [""])[0].strip()
    type_filter = query.get("type", [""])[0].strip()
    flags_filter = query.get("flags", [""])[0].strip()
    try:
        page = max(1, int(query.get("page", ["1"])[0]))
        page_size = min(2000, max(1, int(query.get("pageSize", ["50"])[0])))
    except ValueError:
        page, page_size = 1, 50

    if subject and subject not in ("全部", "全部科目", "所有科目"):
        scopes = [subject]
    else:
        scopes = get_subject_list()

    items = []
    for s in scopes:
        questions = load_questions(s)
        for i, q in enumerate(questions):
            if keyword and keyword not in q.text:
                continue
            if type_filter and not _match_label(q, type_filter):
                continue
            if flags_filter in ("star", "cross", "any"):
                has_star = bool(q.flag_star)
                has_cross = bool(q.flag_cross)
                if flags_filter == "star" and not has_star:
                    continue
                if flags_filter == "cross" and not has_cross:
                    continue
                if flags_filter == "any" and not (has_star or has_cross):
                    continue
            items.append(_q_to_item(q, s, i))

    total = len(items)
    start = (page - 1) * page_size
    return {
        "subject": subject or "全部科目",
        "total": total,
        "page": page,
        "pageSize": page_size,
        "items": items[start:start + page_size],
    }


def handle_add_question(body):
    """新增题目 body: {subject, question:{type,text,answer,options,...}}"""
    subject = (body.get("subject") or "").strip()
    qdata = body.get("question") or {}
    if not subject:
        raise ValueError("缺少科目")
    if not qdata.get("text", "").strip():
        raise ValueError("题干不能为空")
    try:
        q = Question.from_dict(qdata)
    except Exception as e:
        raise ValueError(f"题目数据不合法: {e}")
    q.subject = subject
    questions = load_questions(subject)
    questions.append(q)
    save_questions(subject, questions)
    return {"ok": True, "index": len(questions) - 1, "item": _q_to_item(q, subject, len(questions) - 1)}


def handle_update_question(body):
    """修改题目 body: {subject, index, question:{...}}"""
    subject = (body.get("subject") or "").strip()
    try:
        index = int(body.get("index", -1))
    except (TypeError, ValueError):
        raise ValueError("无效的题目序号")
    qdata = body.get("question") or {}
    questions = load_questions(subject)
    if index < 0 or index >= len(questions):
        raise ValueError("题目序号超出范围")
    try:
        q = Question.from_dict(qdata)
    except Exception as e:
        raise ValueError(f"题目数据不合法: {e}")
    q.subject = subject
    questions[index] = q
    save_questions(subject, questions)
    return {"ok": True, "item": _q_to_item(q, subject, index)}


def _delete_questions(items):
    """
    统一删除题目（单选/批量共用）：按科目分组、组内按 index 降序删除，
    每删一题同步清理错题本记录并移入回收站。
    items: [{subject, index, text?}]（text 用于防错位校验，可为空）
    返回 {deleted, recycled, skipped:[{subject,index,reason}]}
    """
    if not items:
        raise ValueError("未选择任何题目")

    groups = {}
    for it in items:
        subject = (it.get("subject") or "").strip()
        if not subject:
            raise ValueError("缺少科目")
        try:
            index = int(it.get("index", -1))
        except (TypeError, ValueError):
            raise ValueError("无效的题目序号")
        if index < 0:
            raise ValueError("无效的题目序号")
        text = it.get("text")
        groups.setdefault(subject, []).append((index, text))

    deleted = 0
    recycled = 0
    skipped = []

    for subject, lst in groups.items():
        # 去重 + 降序，避免删后序号错位
        order = sorted({k for k, _ in lst}, reverse=True)
        bank = load_questions(subject)
        recycle_items = []
        for index in order:
            if index >= len(bank):
                skipped.append({"subject": subject, "index": index, "reason": "序号超出范围"})
                continue
            q = bank[index]
            # text 校验：防止删除时序号已漂移删错题
            for want_text in [t for k, t in lst if k == index]:
                if want_text is not None and q.text != want_text:
                    skipped.append({"subject": subject, "index": index, "reason": "题目已变化，请刷新后再删"})
                    break
            else:
                del bank[index]
                deleted += 1
                recycle_items.append({
                    "subject": subject,
                    "original_index": index,
                    "item": q.to_dict(),
                })
        save_questions(subject, bank)
        for it in recycle_items:
            remove_wrong_record(subject, it["item"]["text"])  # 同步清理错题本记录
        if recycle_items:
            recycled += len(recycle_items)
            recycle_bin.add(recycle_items)

    return {"deleted": deleted, "recycled": recycled, "skipped": skipped}


def handle_delete_question(query):
    """删除题目 ?subject=&index= （清理错题本记录 + 移入回收站）"""
    subject = query.get("subject", [""])[0]
    try:
        index = int(query.get("index", ["-1"])[0])
    except ValueError:
        raise ValueError("无效的题目序号")
    questions = load_questions(subject)
    if index < 0 or index >= len(questions):
        raise ValueError("题目序号超出范围")
    removed_text = questions[index].text
    result = _delete_questions([{"subject": subject, "index": index, "text": removed_text}])
    if result["deleted"] == 0:
        raise ValueError("题目序号超出范围")
    return {"ok": True, "removed": removed_text, "recycled": True}


def handle_question_flag(body):
    """设置题目标记 body: {subject, index, flag:"star"|"cross", value:bool}"""
    subject = (body.get("subject") or "").strip()
    flag = (body.get("flag") or "").strip()
    if flag not in ("star", "cross"):
        raise ValueError("flag 必须是 star 或 cross")
    value = bool(body.get("value", False))
    try:
        index = int(body.get("index", -1))
    except (TypeError, ValueError):
        raise ValueError("无效的题目序号")
    questions = load_questions(subject)
    if index < 0 or index >= len(questions):
        raise ValueError("题目序号超出范围")
    q = questions[index]
    attr = "flag_star" if flag == "star" else "flag_cross"
    setattr(q, attr, value)
    save_questions(subject, questions)
    return {"ok": True, "item": _q_to_item(q, subject, index)}


def handle_questions_batch_delete(body):
    """批量删除 body: {items:[{subject,index,text}]}（移入回收站）"""
    items = body.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是列表")
    result = _delete_questions(items)
    return {"ok": True, "deleted": result["deleted"], "recycled": result["recycled"], "skipped": result["skipped"]}


def handle_wrong_list(query):
    """错题本列表 ?subject=&type=，返回最新在前"""
    subject = query.get("subject", [""])[0]
    type_filter = query.get("type", [""])[0].strip()
    records = load_wrong_records()
    if subject and subject not in ("全部", "全部科目", "所有科目"):
        records = [r for r in records if r.subject == subject]
    if type_filter and type_filter not in ("全部", ""):
        records = [r for r in records if r.question_type == type_filter]

    # 按时间倒序展示（最新在前），但 index 必须指向错题本文件中的原始顺序，
    # 这样前端按 index 删除时才能删对条目。
    order = sorted(range(len(records)), key=lambda i: records[i].timestamp or "", reverse=True)

    # 为每条记录尝试在题库中解析题目（found=False 表示题目已不存在）
    bank_cache = {}
    items = []
    for raw_idx in order:
        r = records[raw_idx]
        if r.subject not in bank_cache:
            bank_cache[r.subject] = load_questions(r.subject)
        qs = bank_cache[r.subject]
        found_q = next((q for q in qs if q.text == r.question_text), None)
        items.append({
            "index": raw_idx,
            "subject": r.subject,
            "question_type": r.question_type,
            "question_text": r.question_text,
            "correct_answer": r.correct_answer,
            "wrong_answer": r.wrong_answer,
            "timestamp": r.timestamp,
            "found": found_q is not None,
            "question": _q_to_item(found_q, r.subject, qs.index(found_q)) if found_q else None,
        })
    return {"total": len(items), "items": items}


def handle_wrong_delete(query):
    """
    删除错题记录（二选一）：
      ?all=1                          -> 清空错题本
      ?index=N                        -> 删除第 N 条（文件中的顺序）
      ?subject=&question_text=        -> 删除该题的所有错题记录
    """
    if query.get("all", [""])[0] == "1":
        save_wrong_records([])
        return {"ok": True, "message": "错题本已清空"}

    if "index" in query:
        try:
            index = int(query.get("index", ["-1"])[0])
        except ValueError:
            raise ValueError("无效序号")
        records = load_wrong_records()
        if index < 0 or index >= len(records):
            raise ValueError("错题记录序号超出范围")
        records.pop(index)
        save_wrong_records(records)
        return {"ok": True, "message": "已删除该错题记录"}

    subject = query.get("subject", [""])[0]
    question_text = query.get("question_text", [""])[0]
    if not subject or not question_text:
        raise ValueError("缺少参数 subject 或 question_text")
    records = load_wrong_records()
    records = [r for r in records if not (r.subject == subject and r.question_text == question_text)]
    save_wrong_records(records)
    return {"ok": True, "message": "已删除该题的错题记录"}


def _fmt_user_answer(user_answer) -> str:
    if isinstance(user_answer, (list, tuple)):
        return " | ".join(str(x) if str(x) else "（空）" for x in user_answer)
    return str(user_answer or "")


def _bookkeeping(subject: str, q, correct: bool, user_answer, mode: str, exam: bool, owner: str):
    """判分后统一记账：错题本维护 + 平时正确率记录（与终端版一致）"""
    is_wrong_mode = str(mode).endswith("wrong")
    if correct:
        if is_wrong_mode:
            remove_wrong_record(subject, q.text)
    else:
        if is_wrong_mode:
            update_wrong_record_timestamp(subject, q.text)
        else:
            add_wrong_record(subject, q, _fmt_user_answer(user_answer))
    if not is_wrong_mode and not exam:
        records.add_result(owner=owner, subject=subject,
                           type_label=_question_label(q), correct=correct)


def handle_answer(body):
    """
    判定一道题的作答结果（自动判分题型）。
    body: {subject, index, answer(str|list), mode, exam, owner}
    简答题（非自动判分）不在这里判：返回 {correct:null, auto:false, answer:参考答案}，
    由前端展示后调 /api/answer/self 完成记账。
    """
    subject = (body.get("subject") or "").strip()
    user_answer = body.get("answer")
    if user_answer is None:
        user_answer = ""
    mode = body.get("mode") or "all"
    try:
        index = int(body.get("index", -1))
    except (TypeError, ValueError):
        raise ValueError("无效的题目序号")

    questions = load_questions(subject)
    if index < 0 or index >= len(questions):
        raise ValueError("题目序号超出范围")
    q = questions[index]

    if not q.is_auto_graded():
        return {"correct": None, "auto": False, "answer": q.answer_text(),
                "label": _question_label(q), "type": q.get_type_name()}

    correct = q.check_answer(user_answer)
    owner = body.get("owner") or records.DEFAULT_OWNER
    _bookkeeping(subject, q, correct, user_answer, mode, bool(body.get("exam")), owner)
    return {"correct": correct, "answer": q.answer_text(),
            "label": _question_label(q), "type": q.get_type_name()}


def handle_answer_self(body):
    """
    简答题自评记账：body: {subject, index, selfCorrect:bool, answer, mode, exam, owner}
    与自动判分走同一套错题本/正确率记录逻辑。
    """
    subject = (body.get("subject") or "").strip()
    correct = bool(body.get("selfCorrect"))
    try:
        index = int(body.get("index", -1))
    except (TypeError, ValueError):
        raise ValueError("无效的题目序号")
    questions = load_questions(subject)
    if index < 0 or index >= len(questions):
        raise ValueError("题目序号超出范围")
    q = questions[index]
    owner = body.get("owner") or records.DEFAULT_OWNER
    _bookkeeping(subject, q, correct, body.get("answer") or "",
                 body.get("mode") or "all", bool(body.get("exam")), owner)
    return {"ok": True, "correct": correct, "label": _question_label(q)}


def handle_pictures_list(query=None):
    """
    GET /api/pictures[?dir=科目] —— 图片库。
    dir 为空列出 pictures/ 全部（含子目录，name 为相对路径如 数据结构/3.png）；
    指定 dir 时只列该子目录。
    """
    want = ((query or {}).get("dir") or [""])[0].strip()
    if not os.path.isdir(PICTURES_DIR):
        return {"ok": True, "total": 0, "items": []}
    items = []
    base_len = len(PICTURES_DIR)
    for dirpath, _dirnames, filenames in os.walk(PICTURES_DIR):
        rel_dir = dirpath[base_len:].lstrip(os.sep).replace(os.sep, "/")
        if want and rel_dir != want:
            continue
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if os.path.splitext(name)[1].lower() not in _IMG_EXT:
                continue
            rel = f"{rel_dir}/{name}" if rel_dir else name
            items.append({"name": rel, "size": os.path.getsize(os.path.join(dirpath, name))})
    return {"ok": True, "total": len(items), "items": items}


_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_IMG_NAME_RE = re.compile(
    r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff .\-]*\.(?:png|jpe?g|gif|bmp|webp|svg)$", re.IGNORECASE)
_DIR_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff .\-]{0,40}$")


def handle_pictures_upload_raw(name, raw: bytes, dir_name: str = ""):
    """POST /api/pictures/upload?name=xxx[&dir=科目] —— 保存上传的图片字节。
    dir 为空存到 pictures/ 根目录；指定（如科目或 _shared）存到 pictures/<dir>/。
    返回的 name 为带目录前缀的相对路径，直接可用作题干文本中的 token。
    """
    name = (name or "").strip()
    dir_name = (dir_name or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("非法文件名")
    if dir_name and (not _DIR_NAME_RE.match(dir_name) or ".." in dir_name
                     or "/" in dir_name or "\\" in dir_name or dir_name.startswith(".")):
        raise ValueError("非法目录名")
    if not _IMG_NAME_RE.match(name):
        raise ValueError("仅支持 png/jpg/gif/bmp/webp/svg，且文件名不能含路径分隔符")
    if not raw:
        raise ValueError("上传内容为空")
    if len(raw) > _MAX_IMAGE_BYTES:
        raise ValueError("图片超过 8MB 大小限制")
    target_dir = os.path.join(PICTURES_DIR, dir_name) if dir_name else PICTURES_DIR
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, name)
    overwritten = os.path.exists(path)
    tmp = path + ".upload_tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)
    rel = f"{dir_name}/{name}" if dir_name else name
    return {"ok": True, "name": rel, "size": len(raw), "overwritten": overwritten}



def handle_progress_get():
    """读取刷题进度（含 remaining 列表，用于「继续答题」）"""
    p = load_brush_progress()
    if not p:
        return {"exists": False, "progress": None}
    return {"exists": True, "progress": p}


def handle_progress_save(body):
    """保存刷题进度 body: {subject,mode,type_label,remaining,total}"""
    subject = (body.get("subject") or "").strip()
    mode = body.get("mode") or "all"
    remaining = body.get("remaining") or []
    if not isinstance(remaining, list):
        raise ValueError("remaining 必须是列表")
    total = body.get("total", 0)
    progress = {
        "subject": subject,
        "mode": mode,
        "type_label": body.get("type_label"),
        "remaining": remaining,
        "total": total,
    }
    save_brush_progress(progress)
    return {"ok": True}


def handle_progress_clear():
    clear_brush_progress()
    return {"ok": True}


def handle_resolve(body):
    """把 [{subject,text},...] 解析为题库中的序号，供「继续答题」使用"""
    bank_cache = {}
    results = []
    for item in body.get("remaining") or []:
        subject = item.get("subject", "")
        text = item.get("text", "")
        if subject not in bank_cache:
            bank_cache[subject] = load_questions(subject)
        qs = bank_cache[subject]
        found_q = next((q for q in qs if q.text == text), None)
        if found_q is not None:
            results.append({
                "subject": subject,
                "text": text,
                "index": qs.index(found_q),
                "found": True,
                "question": _q_to_item(found_q, subject, qs.index(found_q)),
            })
        else:
            results.append({"subject": subject, "text": text, "index": -1, "found": False, "question": None})
    return {"items": results}


def handle_report_generate(body):
    """根据前端提供的本次会话统计数据生成刷题报告 txt（格式与终端版一致）"""
    start_time = (body.get("start_time") or "").strip()
    end_time = (body.get("end_time") or "").strip() or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subjects = body.get("subjects") or []

    os.makedirs(REPORTS_DIR, exist_ok=True)
    now = datetime.datetime.now()
    filename = f"刷题报告_{now.strftime('%Y%m%d_%H%M%S')}.txt"
    path = os.path.join(REPORTS_DIR, filename)

    lines = ["=== 刷题统计报告 ==="]
    lines.append(f"开始时间：{start_time}")
    lines.append(f"结束时间：{end_time}")

    if start_time:
        try:
            start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            delta = end_dt - start_dt
            hours = delta.seconds // 3600 + delta.days * 24
            minutes = (delta.seconds % 3600) // 60
            lines.append(f"总耗时：{hours}小时{minutes}分钟")
        except ValueError:
            lines.append("总耗时：未知")

    lines.append("")
    grand_total = sum(s.get("total", 0) for s in subjects)
    grand_correct = sum(s.get("correct", 0) for s in subjects)
    grand_wrong = sum(s.get("wrong", 0) for s in subjects)

    for s in sorted(subjects, key=lambda x: x.get("name", "")):
        lines.append(f"【{s.get('name','')}】")
        lines.append(f"刷题总数：{s.get('total', 0)}")
        lines.append(f"正确数：{s.get('correct', 0)}")
        lines.append(f"错误数：{s.get('wrong', 0)}")
        lines.append("")

    lines.append("【总计】")
    lines.append(f"刷题总数：{grand_total}")
    lines.append(f"正确数：{grand_correct}")
    lines.append(f"错误数：{grand_wrong}")
    if grand_total > 0:
        lines.append(f"正确率：{grand_correct / grand_total * 100:.1f}%")
    else:
        lines.append("正确率：0.0%")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {"ok": True, "path": filename}


def handle_report_delete(query):
    """删除报告：DELETE /api/reports?name=<文件名>（永久删除）"""
    name = query.get("name", [""])[0]
    if not name:
        raise ValueError("缺少报告文件名")
    if "/" in name or "\\" in name or ".." in name or not name.lower().endswith(".txt"):
        raise ValueError("非法文件名")
    p = os.path.join(REPORTS_DIR, name)
    if not os.path.isfile(p):
        raise ValueError(f"报告不存在: {name}")
    os.remove(p)
    return {"ok": True, "removed": name}


# ---------------------------------------------------------------- 批量导入（judge）接口 ----------------------------------------------------------------

def _judges():
    """惰性加载 convert_tools 的 judge 注册表"""
    import judges as _ct_judges
    return _ct_judges


def handle_import_judges_list():
    """动态扫描 convert_tools/ 下的 judge，返回数量与清单（文件名即名字）"""
    js = _judges().list_judges()
    return {
        "ok": True,
        "total": len(js),
        "judges": [{"id": j["id"], "name": j["name"], "desc": j["desc"]} for j in js],
    }


def handle_import_preview(body):
    """转换并预览：{subject, judge, text} -> {ok, count, preview}"""
    subject = (body.get("subject") or "").strip()
    judge_id = (body.get("judge") or "").strip()
    text = body.get("text") or ""
    if not subject:
        raise ValueError("缺少科目")
    if not judge_id:
        raise ValueError("缺少转换规则（judge）")
    if not text.strip():
        raise ValueError("请粘贴待转换的原始文本")
    j = _judges().get_judge(judge_id)
    if j is None:
        raise ValueError(f"未知的转换规则: {judge_id}")
    questions = j["parse"](text)
    # 直通 judge（ECHO_RAW）：预览输出 = 原始输入文本；否则用 render 生成排版
    preview = text if j.get("echo_raw") else j["render"](questions)
    return {"ok": True, "count": len(questions), "preview": preview}


def handle_import_apply(body):
    """转换并直接入库：{subject, judge, text} -> {ok, inserted}"""
    subject = (body.get("subject") or "").strip()
    judge_id = (body.get("judge") or "").strip()
    text = body.get("text") or ""
    if not subject:
        raise ValueError("缺少科目")
    if not judge_id:
        raise ValueError("缺少转换规则（judge）")
    if not text.strip():
        raise ValueError("请粘贴待转换的原始文本")
    j = _judges().get_judge(judge_id)
    if j is None:
        raise ValueError(f"未知的转换规则: {judge_id}")
    questions = j["parse"](text)
    if not questions:
        raise ValueError("未识别到任何可导入的题目（请检查文本格式或更换转换规则）")
    bank = load_questions(subject)
    for q in questions:
        q.subject = subject
        bank.append(q)
    save_questions(subject, bank)
    return {"ok": True, "inserted": len(questions)}


def handle_duplicates(query):
    """科目内查重：?subject=&threshold=(50-100) -> {pairs:[{a,b,similarity}]}"""
    subject = query.get("subject", [""])[0]
    if not subject:
        raise ValueError("缺少科目")
    try:
        threshold = int(query.get("threshold", ["60"])[0])
    except ValueError:
        threshold = 60
    threshold = max(50, min(100, threshold))
    return _find_duplicates(subject, threshold=threshold)


# ---------------- 查重后台任务（带进度） ----------------

_dup_jobs = {}
_dup_lock = threading.Lock()
_dup_job_seq = [0]


def _dup_run(job_id, subject, threshold):
    try:
        def _cb(pct):
            with _dup_lock:
                job = _dup_jobs.get(job_id)
                if job:
                    job["percent"] = pct

        result = _find_duplicates(subject, threshold=threshold, progress_cb=_cb)
        with _dup_lock:
            job = _dup_jobs.get(job_id)
            if job:
                job["state"] = "done"
                job["percent"] = 100
                job["result"] = result
    except Exception as e:  # noqa: BLE001
        with _dup_lock:
            job = _dup_jobs.get(job_id)
            if job:
                job["state"] = "error"
                job["error"] = str(e)


def handle_duplicates_start(body):
    """启动后台查重：{subject, threshold} -> {jobId}"""
    subject = (body.get("subject") or "").strip()
    if not subject:
        raise ValueError("缺少科目")
    try:
        threshold = int(body.get("threshold", 60))
    except (TypeError, ValueError):
        threshold = 60
    threshold = max(50, min(100, threshold))

    _dup_job_seq[0] += 1
    job_id = _dup_job_seq[0]
    with _dup_lock:
        _dup_jobs[job_id] = {"state": "running", "percent": 0, "result": None, "error": None}
    threading.Thread(target=_dup_run, args=(job_id, subject, threshold), daemon=True).start()
    return {"ok": True, "jobId": job_id}


def handle_duplicates_progress(query):
    """查询进度：?job=<id> -> {state, percent, error}"""
    try:
        job_id = int(query.get("job", ["0"])[0])
    except ValueError:
        raise ValueError("无效的任务 id")
    with _dup_lock:
        job = _dup_jobs.get(job_id)
        if job is None:
            raise ValueError("查重任务不存在或已完成（结果已取走）")
        return {
            "ok": True,
            "state": job["state"],
            "percent": job.get("percent", 0),
            "error": job.get("error"),
        }


def handle_duplicates_result(query):
    """取回结果：?job=<id> -> {result}（成功后清理任务）"""
    try:
        job_id = int(query.get("job", ["0"])[0])
    except ValueError:
        raise ValueError("无效的任务 id")
    with _dup_lock:
        job = _dup_jobs.get(job_id)
        if job is None:
            raise ValueError("查重任务不存在")
        if job["state"] != "done":
            return {"ok": True, "state": job["state"], "percent": job.get("percent", 0), "error": job.get("error")}
        result = job["result"]
        del _dup_jobs[job_id]
    return {"ok": True, "state": "done", "result": result}



# ---------------------------------------------------------------- 回收站接口 ----------------------------------------------------------------

def _recycle_label(item):
    """由回收的题目 JSON 计算展示标签"""
    if item.get("type") == "选择题":
        return "多选题" if item.get("choice_type") == "multiple" else "单选题"
    return item.get("type") or "未知"


def _recycle_preview(text, max_len=60):
    import re
    t = re.sub(r"\s+", " ", text or "").strip()
    return t[:max_len] + ("..." if len(t) > max_len else "")


def handle_recycle_list(query):
    """回收站列表 ?subject=，最新在前"""
    subject = query.get("subject", [""])[0]
    records = recycle_bin.list_records(subject or None)
    items = []
    for r in records:
        item = r.get("item", {})
        items.append({
            "id": r.get("id"),
            "subject": r.get("subject", ""),
            "original_index": r.get("original_index", 0),
            "deleted_at": r.get("deleted_at", ""),
            "type": item.get("type", ""),
            "label": _recycle_label(item),
            "preview": _recycle_preview(item.get("text", "")),
            "text": item.get("text", ""),
            "answer": item.get("answer", ""),
            "options": item.get("options"),
            "choice_type": item.get("choice_type"),
        })
    return {"ok": True, "total": len(items), "items": items}


def handle_recycle_restore(body):
    """恢复：body {ids:[...]}"""
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError("请选择要恢复的题目")
    restored, missing = recycle_bin.restore(ids)
    return {"ok": True, "restored": restored, "missing": missing}


def handle_recycle_delete(query):
    """彻底删除：all=1 清空 / ids=1,2,3 / id=N"""
    if query.get("all", [""])[0] == "1":
        n = recycle_bin.purge_all()
        return {"ok": True, "purged": n}
    ids_param = query.get("ids", [""])[0] or query.get("id", [""])[0]
    if not ids_param:
        raise ValueError("缺少要删除的记录")
    try:
        ids = [int(x) for x in ids_param.replace("，", ",").split(",") if x.strip()]
    except ValueError:
        raise ValueError("无效的 id")
    n = recycle_bin.purge(ids)
    return {"ok": True, "purged": n}


def handle_records_owners():
    """已有属主列表（账号功能预留接口）"""
    return {"ok": True, "owners": records.list_owners()}


def handle_records_reset(body):
    """重置记录：body {owner?} 或 {all:true}"""
    if body.get("all"):
        n = records.clear_all()
        return {"ok": True, "cleared": n, "message": "全部记录已清空"}
    owner = (body.get("owner") or records.DEFAULT_OWNER)
    n = records.clear_owner(owner)
    return {"ok": True, "cleared": n, "message": f"已清空记录"}


# ---------------------------------------------------------------- HTTP Handler ----------------------------------------------------------------

def _exam_block(owner, subject, rec):
    """考试通过率 = 最近10次模拟考试平均×0.6 + 平时正确率×0.4（不足数据以0补）"""
    mock_avg = exams.avg_last10(owner, subject)
    exam_count = exams.recent_exam_count(owner, subject)
    acc = (rec or {}).get("accuracy")
    acc_val = acc if acc is not None else 0.0
    pass_rate = round(mock_avg * 0.6 + acc_val * 0.4, 1)
    return {"passRate": pass_rate, "mockAvg": round(mock_avg, 1), "examCount": exam_count}


def handle_exam_build(body):
    """加权组卷：按 exam_config 组成，未考过题 +5、错题本中 +4、基础 +1（未考过>错题略大）"""
    subject = (body.get("subject") or "").strip()
    owner = body.get("owner") or exams.DEFAULT_OWNER
    if not subject:
        raise ValueError("缺少科目")
    questions = load_questions(subject)
    if not questions:
        raise ValueError("该科目暂无题目，无法组卷")
    cfg = exam_config.composition_for(subject)
    wrong_texts = {r.question_text for r in load_wrong_records() if r.subject == subject}
    examined = exams.get_examined(owner, subject)

    from collections import defaultdict
    buckets = defaultdict(list)
    for q in questions:
        buckets[_question_label(q)].append(q)
    idx_of = {id(q): i for i, q in enumerate(questions)}

    chosen = []
    chosen_keys = []
    actual = {}
    for label, want in cfg.items():
        pool = list(buckets.get(label, []))
        if want <= 0 or not pool:
            actual[label] = 0
            continue
        weights = []
        for q in pool:
            key = exams.question_key(q)
            w = exam_config.WEIGHT_BASE
            if key not in examined:
                w += exam_config.WEIGHT_NEVER_EXAM
            if q.text in wrong_texts:
                w += exam_config.WEIGHT_IN_WRONG
            weights.append(w)
        picked = []
        take = min(want, len(pool))
        for _ in range(take):
            total = sum(weights)
            r = _random.uniform(0, total)
            acc = 0.0
            pos = len(pool) - 1
            for k in range(len(pool)):
                acc += weights[k]
                if r <= acc:
                    pos = k
                    break
            picked.append(pool.pop(pos))
            weights.pop(pos)
        actual[label] = len(picked)
        for q in picked:
            chosen.append(q)
            chosen_keys.append(exams.question_key(q))

    if not chosen:
        raise ValueError("没有可抽的题目")
    _random.shuffle(chosen)
    exams.mark_examined(owner, subject, chosen_keys)
    items = [_q_to_item(q, subject, idx_of[id(q)]) for q in chosen]
    return {"ok": True, "subject": subject, "composition": actual, "items": items}


def handle_exam_save(body):
    """保存一次模拟考试成绩 {subject, score(0-100)}"""
    subject = (body.get("subject") or "").strip()
    owner = body.get("owner") or exams.DEFAULT_OWNER
    if not subject:
        raise ValueError("缺少科目")
    try:
        score = float(body.get("score", 0))
    except (TypeError, ValueError):
        raise ValueError("无效的成绩")
    score = max(0.0, min(100.0, score))
    scores = exams.save_score(owner, subject, score)
    return {"ok": True, "saved": True, "count": len(scores)}




# ---------------------------------------------------------------- 题库远程更新 ----------------------------------------------------------------

def handle_bank_info():
    """GET /api/bank/info —— 查看题库远程仓库配置（不联网）"""
    try:
        owner, repo, branch, sources, src = sync_bank._resolve_remote()
        return {"ok": True, "configured": True, "error": None,
                "remote": {"owner": owner, "repo": repo, "branch": branch,
                           "url": f"https://github.com/{owner}/{repo}", "source": src},
                "sources": sources}
    except sync_bank.SyncError as e:
        return {"ok": False, "configured": False, "error": str(e), "remote": None}


def handle_bank_check():
    """GET /api/bank/check —— 联网检查题库是否有更新"""
    return sync_bank.check_update()


def handle_bank_update():
    """POST /api/bank/update —— 下载并应用题库更新（自动备份）"""
    return sync_bank.apply_update()




class ApiHandler(BaseHTTPRequestHandler):
    """静态文件 + JSON API 的统一入口"""

    server_version = "ShuatiWeb/1.0"

    # ---- 基础工具 ----

    def log_message(self, fmt, *args):  # 关掉默认冗长日志，改走自己的简洁日志
        pass

    def _log(self, method, path, code):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            sys.stderr.write(f"[{ts}] {method} {path} -> {code}\n")
            sys.stderr.flush()
        except Exception:
            pass

    def _send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, code, message):
        self._send_json({"ok": False, "error": message}, code)

    def _send_binary(self, data, ctype, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            import urllib.parse as _up
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{_up.quote(filename)}")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8")) or {}
        except (ValueError, UnicodeDecodeError):
            raise ValueError("请求体不是合法的 JSON")

    def _route_path(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        return path, query

    # ---- 业务路由 ----

    def _handle_api(self, method, path, query):
        try:
            if method == "GET":
                if path == "/api/archive/save":
                    r = archive_manager.create_archive()
                    self._send_json({"ok": True, **r})
                elif path == "/api/archive/download":
                    name = query.get("name", [""])[0]
                    if not archive_manager.safe_archive_name(name):
                        self._send_error_json(400, "非法存档文件名")
                        return
                    self._send_binary(archive_manager.read_archive_bytes(name),
                                      "application/zip", filename=name)
                elif path == "/api/overview":
                    self._send_json(handle_overview(query))
                elif path == "/api/records/owners":
                    self._send_json(handle_records_owners())
                elif path == "/api/bank/info":
                    self._send_json(handle_bank_info())
                elif path == "/api/bank/check":
                    self._send_json(handle_bank_check())
                elif path == "/api/pictures":
                    self._send_json(handle_pictures_list(query))
                elif path == "/api/questions":
                    self._send_json(handle_questions(query))
                elif path == "/api/wrong":
                    self._send_json(handle_wrong_list(query))
                elif path == "/api/duplicates":
                    self._send_json(handle_duplicates(query))
                elif path == "/api/duplicates/progress":
                    self._send_json(handle_duplicates_progress(query))
                elif path == "/api/duplicates/result":
                    self._send_json(handle_duplicates_result(query))
                elif path == "/api/recycle":
                    self._send_json(handle_recycle_list(query))
                elif path == "/api/progress":
                    self._send_json(handle_progress_get())
                elif path == "/api/reports":
                    self._send_json(self._list_reports())
                elif path.startswith("/api/reports/"):
                    name = path[len("/api/reports/"):]
                    self._send_json(self._read_report(name))
                elif path == "/api/import/judges":
                    self._send_json(handle_import_judges_list())
                else:
                    self._send_error_json(404, f"未找到接口: {path}")

            elif method == "POST":
                if path == "/api/archive/restore":
                    # 原始 zip 上传恢复（非 JSON）
                    length = int(self.headers.get("Content-Length") or 0)
                    if length <= 0 or length > archive_manager.MAX_ARCHIVE_BYTES:
                        raise ValueError("存档为空或超过大小限制")
                    raw = self.rfile.read(length)
                    backup_name = archive_manager.backup_now("restore_before")
                    res = archive_manager.restore_archive(raw)
                    self._send_json({"ok": True, "backup": backup_name, **res})
                    return
                if path == "/api/pictures/upload":
                    name = (query.get("name") or [""])[0]
                    dir_name = (query.get("dir") or [""])[0]
                    length = int(self.headers.get("Content-Length") or 0)
                    if length <= 0 or length > _MAX_IMAGE_BYTES:
                        raise ValueError("图片为空或超过 8MB 大小限制")
                    raw = self.rfile.read(length)
                    self._send_json(handle_pictures_upload_raw(name, raw, dir_name))
                    return
                body = self._read_body()
                if path == "/api/questions":
                    self._send_json(handle_add_question(body))
                elif path == "/api/questions/flag":
                    self._send_json(handle_question_flag(body))
                elif path == "/api/questions/batch-delete":
                    self._send_json(handle_questions_batch_delete(body))
                elif path == "/api/answer":
                    self._send_json(handle_answer(body))
                elif path == "/api/answer/self":
                    self._send_json(handle_answer_self(body))
                elif path == "/api/progress":
                    self._send_json(handle_progress_save(body))
                elif path == "/api/resolve":
                    self._send_json(handle_resolve(body))
                elif path == "/api/reports":
                    self._send_json(handle_report_generate(body))
                elif path == "/api/import/preview":
                    self._send_json(handle_import_preview(body))
                elif path == "/api/import/apply":
                    self._send_json(handle_import_apply(body))
                elif path == "/api/recycle/restore":
                    self._send_json(handle_recycle_restore(body))
                elif path == "/api/records/reset":
                    self._send_json(handle_records_reset(body))
                elif path == "/api/bank/update":
                    self._send_json(handle_bank_update())
                elif path == "/api/exams/build":
                    self._send_json(handle_exam_build(body))
                elif path == "/api/exams/save":
                    self._send_json(handle_exam_save(body))
                elif path == "/api/duplicates/start":
                    self._send_json(handle_duplicates_start(body))
                else:
                    self._send_error_json(404, f"未找到接口: {path}")

            elif method == "PUT":
                body = self._read_body()
                if path == "/api/questions":
                    self._send_json(handle_update_question(body))
                else:
                    self._send_error_json(404, f"未找到接口: {path}")

            elif method == "DELETE":
                if path == "/api/questions":
                    self._send_json(handle_delete_question(query))
                elif path == "/api/recycle":
                    self._send_json(handle_recycle_delete(query))
                elif path == "/api/reports":
                    self._send_json(handle_report_delete(query))
                elif path == "/api/wrong":
                    self._send_json(handle_wrong_delete(query))
                elif path == "/api/progress":
                    self._send_json(handle_progress_clear())
                else:
                    self._send_error_json(404, f"未找到接口: {path}")
            else:
                self._send_error_json(405, f"不支持的方法: {method}")

        except ValueError as e:
            self._send_error_json(400, str(e))
        except Exception as e:  # 兜底，避免服务崩溃
            import traceback
            traceback.print_exc()
            self._send_error_json(500, f"服务器内部错误: {e}")

    # ---- 报告读取 ----

    def _list_reports(self):
        if not os.path.isdir(REPORTS_DIR):
            return {"total": 0, "items": []}
        names = []
        for n in os.listdir(REPORTS_DIR):
            p = os.path.join(REPORTS_DIR, n)
            if n.lower().endswith(".txt") and os.path.isfile(p):
                names.append({
                    "name": n,
                    "size": os.path.getsize(p),
                    "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S"),
                })
        names.sort(key=lambda x: x["mtime"], reverse=True)
        return {"total": len(names), "items": names}

    def _read_report(self, name):
        if not name or "/" in name or "\\" in name or ".." in name:
            raise ValueError("非法文件名")
        p = os.path.join(REPORTS_DIR, name)
        if not os.path.isfile(p):
            raise ValueError(f"报告不存在: {name}")
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return {"name": name, "content": f.read()}

    # ---- 静态文件 ----

    def _serve_static(self, path):
        # /pictures/xxx 映射到项目 pictures 目录
        if path.startswith("/pictures/"):
            rel = path[len("/pictures/"):]
            base, name = PICTURES_DIR, rel
        else:
            # 其余全部映射到 webui 静态目录
            base, name = WEBUI_DIR, path.lstrip("/") or "index.html"

        full = os.path.normpath(os.path.join(base, name))
        if not full.startswith(os.path.normpath(base)):
            self._send_error_json(403, "非法路径")
            return

        if not os.path.isfile(full):
            self._send_error_json(404, "文件不存在")
            return

        ext = os.path.splitext(full)[1].lower()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ext == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif ext in (".html", ".css"):
            ctype = f"text/{ext[1:]}; charset=utf-8"

        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            self._send_error_json(500, "读取文件失败")
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ---- 入口 ----

    def _dispatch(self, method):
        path, query = self._route_path()
        try:
            if path.startswith("/api/"):
                self._handle_api(method, path, query)
                self._log(method, path, "api")
            else:
                self._serve_static(path)
                self._log(method, path, "static")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._send_error_json(500, "服务器内部错误")
            except Exception:
                pass

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


# ---------------------------------------------------------------- 启动 ----------------------------------------------------------------

def parse_port(argv):
    port = 8000
    no_browser = False
    host = "127.0.0.1"
    i = 0
    while i < len(argv):
        if argv[i] == "--port" and i + 1 < len(argv):
            try:
                port = int(argv[i + 1])
            except ValueError:
                port = 8000
            i += 2
        elif argv[i] == "--host" and i + 1 < len(argv):
            host = argv[i + 1]
            i += 2
        elif argv[i] == "--no-browser":
            no_browser = True
            i += 1
        else:
            i += 1
    return host, port, no_browser


def start_server(host="127.0.0.1", port=8000, open_browser=True):
    """启动网页版服务（阻塞运行）；返回 server 对象前先做路径检查"""
    if not os.path.isdir(WEBUI_DIR):
        raise FileNotFoundError(f"未找到前端静态目录: {WEBUI_DIR}")
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    httpd = ThreadingHTTPServer((host, port), ApiHandler)
    url = f"http://{host}:{port}"

    print("=" * 58)
    print("  刷题软件 - 网页版已启动")
    print(f"  请在浏览器中打开: {url}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 58)

    if open_browser:
        import webbrowser

        def _open():
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Timer(0.8, _open).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    host, port, no_browser = parse_port(sys.argv[1:])
    start_server(host=host, port=port, open_browser=not no_browser)
