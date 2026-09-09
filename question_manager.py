"""
题目与错题本的增删改查模块
使用 JSON 文件存储
"""

import json
import os
from typing import List, Optional, Tuple, Dict, Any
from models.question import Question, QuestionFactory
from models.wrong_record import WrongRecord
from utils.helpers import (
    ensure_data_dir,
    get_subject_filename,
    get_wrong_book_filename,
    get_progress_filename,
    get_subject_list,
)


def load_questions(subject: str) -> List[Question]:
    """加载指定科目的所有题目"""
    ensure_data_dir()
    filename = get_subject_filename(subject)
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as f:
        data_list = json.load(f)
    questions = []
    for data in data_list:
        try:
            q = Question.from_dict(data)
            q.subject = subject
            questions.append(q)
        except (ValueError, KeyError) as e:
            print(f"   [警告] 加载题目时跳过一条无效数据: {e}")
    return questions


def save_questions(subject: str, questions: List[Question]):
    """保存题目到指定科目的题库"""
    ensure_data_dir()
    filename = get_subject_filename(subject)
    data_list = [q.to_dict() for q in questions]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)


def add_question(subject: str, question: Question):
    """向指定科目的题库添加一道题"""
    questions = load_questions(subject)
    questions.append(question)
    save_questions(subject, questions)


def get_question_counts(subjects: Optional[List[str]] = None) -> Dict[str, int]:
    """统计各科目的题目数量，返回 {科目: 题数}；默认统计全部科目"""
    if subjects is None:
        subjects = get_subject_list()
    return {subj: len(load_questions(subj)) for subj in subjects}


def load_wrong_records() -> List[WrongRecord]:
    """加载错题本"""
    ensure_data_dir()
    filename = get_wrong_book_filename()
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as f:
        data_list = json.load(f)
    return [WrongRecord.from_dict(d) for d in data_list]


def save_wrong_records(records: List[WrongRecord]):
    """保存错题本"""
    ensure_data_dir()
    filename = get_wrong_book_filename()
    data_list = [r.to_dict() for r in records]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)


def add_wrong_record(subject: str, question: Question, wrong_answer: str):
    """添加一条错题记录"""
    records = load_wrong_records()
    record = WrongRecord(
        subject=subject,
        question_text=question.text,
        question_type=question.get_type_name(),
        correct_answer=question.answer,
        wrong_answer=wrong_answer,
    )
    records.append(record)
    save_wrong_records(records)


def remove_wrong_record(subject: str, question_text: str):
    """从错题本中移除指定题目"""
    records = load_wrong_records()
    records = [
        r
        for r in records
        if not (r.subject == subject and r.question_text == question_text)
    ]
    save_wrong_records(records)


def update_wrong_record_timestamp(subject: str, question_text: str):
    """
    更新错题记录的时间戳（做错时先移除再重新加入）
    返回新的 WrongRecord 对象
    """
    records = load_wrong_records()
    target = None
    remaining = []
    for r in records:
        if r.subject == subject and r.question_text == question_text:
            target = r
        else:
            remaining.append(r)
    if target:
        # 重新加入（更新时间戳）
        new_record = WrongRecord(
            subject=target.subject,
            question_text=target.question_text,
            question_type=target.question_type,
            correct_answer=target.correct_answer,
            wrong_answer=target.wrong_answer,
        )
        remaining.append(new_record)
        save_wrong_records(remaining)
        return new_record
    return None


def get_wrong_records_by_subject(subject: str) -> List[WrongRecord]:
    """获取指定科目的错题记录"""
    all_records = load_wrong_records()
    if subject == "所有科目":
        return all_records
    return [r for r in all_records if r.subject == subject]


def get_wrong_question_count(subject: str) -> int:
    """获取指定科目的错题数量"""
    return len(get_wrong_records_by_subject(subject))


def clear_all_wrong_records():
    """清空整个错题本"""
    save_wrong_records([])
    print("  ✓ 错题本已清空")


def search_questions(keyword: str) -> List[Tuple[int, str, Question]]:
    """
    在所有科目中搜索题目文本包含关键词的题目
    返回 [(序号, 科目, Question对象)]
    """
    subjects = get_subject_list()
    results = []
    idx = 1
    for subj in subjects:
        questions = load_questions(subj)
        for q in questions:
            if keyword in q.text:
                results.append((idx, subj, q))
                idx += 1
    return results


# ==================== 刷题进度管理 ====================

def save_brush_progress(data: Dict[str, Any]):
    """保存刷题进度"""
    ensure_data_dir()
    filename = get_progress_filename()
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_brush_progress() -> Optional[Dict[str, Any]]:
    """读取刷题进度，无文件时返回 None"""
    filename = get_progress_filename()
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_brush_progress():
    """删除刷题进度文件"""
    filename = get_progress_filename()
    if os.path.exists(filename):
        os.remove(filename)


def has_brush_progress() -> bool:
    """判断是否有刷题进度"""
    filename = get_progress_filename()
    return os.path.exists(filename)
