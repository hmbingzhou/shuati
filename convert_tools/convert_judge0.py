# -*- coding: utf-8 -*-
"""直通 judge（convert_judge0）：输入原样变输出，同时识别"已处理格式"文本中的题目。

用途：把已经处理好的文本（text.txt）原样复制为输出（text_converted.txt），
并解析其中的题目数量/内容，供网页预览与（可选）入库。

解析的"已处理格式"（本项目 text_converted 排版）：
    题干（可多行）
    (空行)
    选项文本（每行一个，可能没有——判断题）
    (空行)
    答案行（判断题：T/F 或 对/错/√/×/正确/错误；选择题：单个纯字母行 A/AC）
    （答案行后紧接下一题题干，无空行）
判断题答案归一化为"正确/错误"；选择题答案字母≥2 视为多选。
"""

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models.question import TrueFalseQuestion, ChoiceQuestion, FillBlankQuestion  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_DESC = "直通：输入原样输出，识别判断题、选择题与填空题"
ECHO_RAW = True  # 调用方据此把"原始输入文本"作为输出，而不是 render 的结果

# 判断题答案行（整行单值）；交给 TrueFalseQuestion 构造函数归一化
_TF_TOKENS = {"T", "F", "t", "f", "对", "错", "正确", "错误", "√", "×"}


def parse(text):
    """解析"已处理格式"文本：优先判定词(判断题) -> 选项+字母(选择题) -> 题干+文本答案(填空题)"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    n = len(lines)
    questions = []
    i = 0
    while i < n:
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            break

        # 题干块：读到空行为止
        stem_lines = []
        while i < n and lines[i].strip():
            stem_lines.append(lines[i].strip())
            i += 1
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            break

        first = lines[i].strip()
        stem = "\n".join(stem_lines).strip()

        # 1) 判断题：题干后直接是单独一行的判定词
        if first in _TF_TOKENS:
            i += 1
            questions.append(TrueFalseQuestion(text=stem, answer=first))
            continue

        # 2) 选择题：题干后是 ≥2 行选项，空行后是纯字母答案行（用向前扫描判定，不破坏填空流程）
        j = i
        while j < n and lines[j].strip():
            j += 1
        k = j
        while k < n and not lines[k].strip():
            k += 1
        option_lines = [lines[t].strip() for t in range(i, j)]
        next_token = lines[k].strip() if k < n else ""
        # 填空占位标记（【第N空…】）出现则不是选择题（真实选择题选项不会有该标记）
        has_blank_marker = any("【" in o or "】" in o or "第" in o and "空" in o for o in option_lines)
        if (not has_blank_marker and len(option_lines) >= 2
                and re.fullmatch(r"[A-Za-z]+", next_token) and len(option_lines) <= 26):
            letters = next_token.upper()
            options = [o for o in option_lines if o.strip()]
            if 2 <= len(options) <= 26 and all(ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:len(options)] for ch in letters):
                opts = [("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[t], o) for t, o in enumerate(options)]
                i = k + 1
                if len(letters) >= 2:
                    questions.append(ChoiceQuestion(
                        text=stem, options=opts, answer=letters, choice_type="multiple",
                        multiple_answers=list(letters),
                    ))
                else:
                    questions.append(ChoiceQuestion(
                        text=stem, options=opts, answer=letters[0], choice_type="single",
                        multiple_answers=None,
                    ))
                continue

        # 3) 填空题：空行后的首行即答案，其后行视为下一题题干继续解析
        if stem:
            questions.append(FillBlankQuestion(text=stem, answer=first))
        i += 1  # 只消费答案这一行；同一 run 里的后续行交给下一轮当题干读取
    return questions


def render(questions):
    """直通 judge 的输出以原始文本为准（ECHO_RAW）；此处为标准排版兜底，供非直通场景调用"""
    out = []
    for q in questions:
        out.append(q.text)
        out.append('')
        if isinstance(q, ChoiceQuestion):
            for _, opt in (q.options or []):
                out.append(opt)
            out.append('')
        out.append('T' if q.answer == "正确" else ('F' if q.answer == "错误" else q.answer))
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    questions = parse(content)
    print(f'识别到 {len(questions)} 道题（已处理格式）')
    # 直通：原样写入
    with open(os.path.join(BASE, 'text_converted.txt'), 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'已将 text.txt 原样写入 text_converted.txt（{len(content.splitlines())} 行）')


if __name__ == '__main__':
    main()
