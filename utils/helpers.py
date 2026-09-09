"""
辅助函数
"""

import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def ensure_data_dir():
    """确保data目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def get_subject_filename(subject: str) -> str:
    """获取科目对应的题库文件名"""
    safe = subject.replace(" ", "_")
    return os.path.join(DATA_DIR, f"{safe}.json")


def get_wrong_book_filename() -> str:
    """获取错题本文件名"""
    return os.path.join(DATA_DIR, "wrong_book.json")


def get_progress_filename() -> str:
    """获取刷题进度文件名"""
    return os.path.join(DATA_DIR, "brush_progress.json")


# 年级顺序（按学期）
GRADE_ORDER = [
    "大一上",
    "大一下",
    "大二上",
    "大二下",
    "大三上",
    "大三下",
    "大四上",
    "大四下",
]

# 年级 -> 科目列表
GRADE_SUBJECTS = {
    "大一上": ["C语言", "中国近现代史纲要", "思想道德与法治", "软件工程引论"],
    "大一下": ["Java", "数据结构", "马克思主义基本原理"],
    "大二上": [
        "计算机组成原理",
        "计算机网络技术",
        "毛泽东思想和中国特色理论体系概论",
        "Python",
        "数据库原理",
    ],
    "大二下": [],
    "大三上": [],
    "大三下": [],
    "大四上": [],
    "大四下": [],
}


def get_grade_list() -> list:
    """获取所有年级列表（按学期顺序）"""
    return list(GRADE_ORDER)


def get_subjects_by_grade(grade: str) -> list:
    """获取指定年级下的科目列表"""
    return list(GRADE_SUBJECTS.get(grade, []))


def get_subject_list() -> list:
    """获取全部科目列表（按年级顺序展平、去重）"""
    seen = set()
    subjects = []
    for grade in GRADE_ORDER:
        for subj in GRADE_SUBJECTS.get(grade, []):
            if subj not in seen:
                seen.add(subj)
                subjects.append(subj)
    return subjects

# 颜色工具函数（放代码开头）
def green(text):
    return f"\033[1;32m{text}\033[0m"

def red(text):
    return f"\033[1;31m{text}\033[0m"

def yellow(text):
    return f"\033[1;33m{text}\033[0m"