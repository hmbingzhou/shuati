# -*- coding: utf-8 -*-
"""转换选择题 v5：无题号、无字母前缀的纯文本选项，每题后跟字母答案行。

适用文本结构（如中国近现代史类单选题）：
    题干（…）
    (空行)
    选项1
    选项2
    选项3
    选项4
    (空行)
    A            ← 单行字母答案（AC 之类视为多选）
    (空行)
    …

作为 convert_tools 的 judge 插件使用（文件名即 id/名字）；
也可直接运行：读取本目录 text.txt，把转换结果写入本目录 text_converted.txt。
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models.question import ChoiceQuestion  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_DESC = "选择题：无题号纯文本选项，每题后跟字母答案行"


def _build_choice(stem_lines, option_lines, letters):
    """由题干行/选项行/字母答案构建单选题或多选题；无效返回 None"""
    stem = "\n".join(stem_lines).strip()
    options = [o for o in option_lines if o.strip()]
    if not stem or len(options) < 2 or not letters:
        return None
    if len(options) > 26:
        return None  # 选项数超过 A-Z 可表达范围，跳过（多为格式误判）
    opts = [("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i], o) for i, o in enumerate(options)]
    valid = [l for l, _ in opts]
    bad = [ch for ch in letters if ch not in valid]
    if bad:
        return None  # 答案字母超出选项范围
    if len(letters) >= 2:
        return ChoiceQuestion(
            text=stem, options=opts, answer=letters, choice_type="multiple",
            multiple_answers=list(letters),
        )
    return ChoiceQuestion(
        text=stem, options=opts, answer=letters[0], choice_type="single",
        multiple_answers=None,
    )


def _scan(text):
    """
    解析“题干 → 空行 → 纯文本选项 → 空行 → 字母答案行(后面紧跟下一题题干)”格式。

    关键结构特征：题干与选项、选项与答案之间有空行；答案行与下一题题干之间
    通常没有空行，因此答案行用“单独一行的纯字母”来识别。
    """
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n = len(raw_lines)
    questions = []
    i = 0
    while i < n:
        # 跳过杂散空行
        while i < n and not raw_lines[i].strip():
            i += 1
        if i >= n:
            break

        # 题干块：读到空行为止（可能多行）
        stem_lines = []
        while i < n and raw_lines[i].strip():
            stem_lines.append(raw_lines[i].strip())
            i += 1
        while i < n and not raw_lines[i].strip():
            i += 1

        # 选项块：读到空行为止
        option_lines = []
        while i < n and raw_lines[i].strip():
            option_lines.append(raw_lines[i].strip())
            i += 1
        while i < n and not raw_lines[i].strip():
            i += 1

        if i >= n:
            break
        ans_token = raw_lines[i].strip()
        if not re.fullmatch(r"[A-Za-z]+", ans_token):
            # 没有字母答案行：跳过这一行继续，避免死循环（该组不计入）
            i += 1
            continue
        letters = ans_token.upper()
        i += 1  # 消费答案行；其后若紧跟下一题题干则交给下一轮读取

        q = _build_choice(stem_lines, option_lines, letters)
        if q is not None:
            questions.append(q)
    return questions


def parse(text):
    """解析为可入库的选择题对象（单选/多选）"""
    return _scan(text)


def render(questions):
    """text_converted 排版：题干 / 空行 / 选项每行一个 / 空行 / 答案字母"""
    out = []
    for q in questions:
        out.append(q.text)
        out.append('')
        for _, opt in (q.options or []):
            out.append(opt)
        out.append('')
        out.append(q.answer)
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    questions = parse(content)
    print(f'找到 {len(questions)} 个题目')
    for idx, q in enumerate(questions):
        preview = q.text[:50].replace('\n', '\\n')
        print(f'  [{idx}] {preview}... ({len(q.options)} 选项) -> {q.answer}')
    output = render(questions)
    with open(os.path.join(BASE, 'text_converted.txt'), 'w', encoding='utf-8') as f:
        f.write(output)
    print(f'\n总行数: {len(output.split(chr(10)))}')
    print('\n--- 转换结果预览（前20行）---')
    for li, line in enumerate(output.split('\n')[:20], 1):
        if line == '':
            print('  (blank)')
        else:
            print(f'  {line}')


if __name__ == '__main__':
    main()
