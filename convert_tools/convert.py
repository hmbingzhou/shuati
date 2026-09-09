# -*- coding: utf-8 -*-
"""Convert text.txt quiz format to the specified format.

通用转换：读取"题号+选项+末尾答案汇总行"风格的原始文本，解析为选择题。

Rules:
1. Delete question numbers (remove leading "数字．" or "数字、")
2. Delete trailing parentheses from question stem only (( ) or （ ）)
3. Each option on its own line, remove "A．", "B．" etc. prefixes
4. Split answer line per question, place below each question's options
5. Blank line after stem, blank line after options (before answer)
6. No blank line between answer and next question's stem

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
JUDGE_DESC = "通用选择题：题号+选项+末尾答案汇总行"


def is_stem_line(line):
    """Check if a line is a question stem (starts with number + separator)."""
    return bool(re.match(r'^\d+[lL]?[．、.，]', line.strip()))


def is_answer_line(line):
    """Check if a line is a pure answer line (number+separator+letter patterns only)."""
    cleaned = re.sub(r'\d+\s*[．、.，。]\s*[A-E]+\s*', '', line)
    return cleaned.strip() == ''


def remove_question_number(line):
    """Remove leading question number like '1．', '2、', '11.', etc."""
    return re.sub(r'^\d+[lL]?[．、.，]\s*', '', line).strip()


def remove_trailing_parens(line):
    """Remove trailing ( ) or （ ） only at the end of the stem."""
    line = re.sub(r'\s*[(（]\s*[)）]\s*$', '', line)
    return line.strip()


def split_options_from_line(line):
    """Split a line containing multiple options into individual option texts."""
    parts = re.split(r'[A-E]\s*[．、.。，]+', line)
    options = [p.strip() for p in parts if p.strip()]
    return options


def parse_answer_lines(answer_lines):
    """Parse multiple answer lines into {question_number: answer_string}."""
    answers = {}
    full_text = ''.join(answer_lines).replace(' ', '')
    for m in re.finditer(r'(\d+)\s*[．、.。，]\s*([A-E]+)', full_text):
        qnum = int(m.group(1))
        ans = m.group(2)
        answers[qnum] = ans
    return answers


def _scan(text):
    """复刻原转换解析，返回 [(stem, [option_texts], raw_answer|'')]"""
    lines = [l.strip() for l in text.strip().split('\n')]

    # Remove trailing blank lines
    while lines and lines[-1] == '':
        lines.pop()

    # Scan from the end to collect all answer lines
    answer_lines = []
    idx = len(lines) - 1
    while idx >= 0 and is_answer_line(lines[idx]):
        answer_lines.insert(0, lines[idx])
        idx -= 1

    question_lines = [l for l in lines[:idx + 1] if l]

    answers = parse_answer_lines(answer_lines)

    questions = []  # [(stem, [options])]
    current_stem = None
    current_options = []

    for line in question_lines:
        if is_stem_line(line):
            if current_stem is not None:
                questions.append((current_stem, current_options))
            current_stem = remove_question_number(line)
            current_stem = remove_trailing_parens(current_stem)
            current_options = []
        else:
            current_options.extend(split_options_from_line(line))

    if current_stem is not None:
        questions.append((current_stem, current_options))

    records = []
    for i, (stem, opts) in enumerate(questions):
        ans = answers.get(i + 1, '')
        records.append({"text": stem, "options": opts, "raw_answer": ans or None})
    return records


def parse(text):
    """解析为可入库的选择题对象（单/多选），无有效答案/题干/选项的跳过"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # 兼容 Windows 换行
    qs = []
    for r in _scan(text):
        letters = re.sub(r'[^A-Ea-e]', '', r["raw_answer"] or "").upper()
        if not r["text"].strip() or not r["options"] or not letters:
            continue
        if len(r["options"]) > 26:
            continue  # 选项数超过 A-Z 可表达范围，跳过（多为格式误判）
        options = [("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i], t) for i, t in enumerate(r["options"])]
        if len(letters) >= 2:
            qs.append(ChoiceQuestion(
                text=r["text"], options=options, answer=letters, choice_type="multiple",
                multiple_answers=list(letters),
            ))
        else:
            qs.append(ChoiceQuestion(
                text=r["text"], options=options, answer=letters[0], choice_type="single",
                multiple_answers=None,
            ))
    return qs


def render(questions):
    """生成 text_converted 排版：题干 / 空行 / 选项 / 空行 / 答案；末尾空行去除"""
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
    records = _scan(content)
    print(f'找到 {len(records)} 个题目')
    for idx, r in enumerate(records):
        preview = r["text"][:60].replace('\n', '\\n')
        print(f'  [{idx}] {preview}... ({len(r["options"])} 选项) -> {r["raw_answer"]}')
    questions = parse(content)
    print(f'可导入 {len(questions)} 道（跳过无有效答案的 {len(records) - len(questions)} 道）')
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
