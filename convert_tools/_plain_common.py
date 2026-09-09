# -*- coding: utf-8 -*-
"""
judge1-6（纯文本格式）共享工具
==============================
文件以 _ 开头，不会被 convert_tools/judges.py 当作 judge 加载。

通用结构（judge1/2/3/5 共用）：
    题干行（可多行，读到空行为止）
    (空行)
    [选项/答案…]
答案行“紧跟”下一题题干（之间可以没有空行），因此答案按行读取，
不能用“空行分段”的块来切。
"""

import re

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def normalize_lines(text):
    """统一换行后按行拆分"""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def read_block(lines, i):
    """从 i 开始：跳过空行后收集连续非空行（去两端空白），返回 (block, 下一个下标)"""
    n = len(lines)
    while i < n and not lines[i].strip():
        i += 1
    block = []
    while i < n and lines[i].strip():
        block.append(lines[i].strip())
        i += 1
    return block, i


def skip_blank(lines, i):
    n = len(lines)
    while i < n and not lines[i].strip():
        i += 1
    return i


def letters_of(token):
    """从字符串中取出大写字母序列（忽略空格/顿号/标点）"""
    return "".join(re.findall(r"[A-Za-z]", str(token or ""))).upper()


def make_choice(stem, options, letters):
    """
    由题干/选项/答案字母构建 ChoiceQuestion（选项数在 2..26 且答案字母都在范围内）。
    返回 None 表示无法构建。
    """
    if not stem or not options or not letters:
        return None
    if len(options) < 2 or len(options) > 26:
        return None
    from models.question import ChoiceQuestion  # 延迟导入避免循环
    opts = [(LETTERS[i], o) for i, o in enumerate(options)]
    valid = {l for l, _ in opts}
    if any(ch not in valid for ch in letters):
        return None
    if len(letters) >= 2:
        return ChoiceQuestion(text=stem, options=opts, answer=letters,
                              choice_type="multiple", multiple_answers=list(letters))
    return ChoiceQuestion(text=stem, options=opts, answer=letters[0],
                          choice_type="single", multiple_answers=None)


def make_tf(stem, token):
    """把答案 token 归一化构造成判断题；无法识别返回 None"""
    from models.question import TrueFalseQuestion  # 延迟导入
    if not stem or not token:
        return None
    norm = str(token).strip()
    if not norm:
        return None
    low = norm.lower()
    if low not in TrueFalseQuestion.TF_MAP and norm not in ("正确", "错误"):
        return None
    return TrueFalseQuestion(text=stem, answer=norm)
