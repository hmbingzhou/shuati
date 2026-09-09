# -*- coding: utf-8 -*-
"""转换选择题 v3：提取题干 + 选项文本 + 答案字母（答案来自末尾汇总行）。

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
JUDGE_DESC = "选择题：从文件末尾的 A-D 字母答案行读取答案"

META_LINES = {'评测结果', '答案正确', '答案错误', '得分'}


def _letters_to_choice(text, option_texts, letters):
    """按答案字母数构建单选/多选题对象；无法构建返回 None"""
    letters = (letters or "").strip().upper().replace(" ", "")
    letters = re.sub(r'[^A-Z]', '', letters)
    if not text.strip() or not option_texts or not letters:
        return None
    if len(option_texts) > 26:
        return None  # 选项数超过 A-Z 可表达范围，跳过（多为格式误判）
    options = [(LETTERS[i], t) for i, t in enumerate(option_texts)]
    if len(letters) >= 2:
        return ChoiceQuestion(
            text=text, options=options, answer=letters, choice_type="multiple",
            multiple_answers=list(letters),
        )
    return ChoiceQuestion(
        text=text, options=options, answer=letters[0], choice_type="single",
        multiple_answers=None,
    )


LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _scan(text):
    """复刻原转换解析，返回 [(question_text, [option_texts], raw_answer_letters|None)]"""
    lines = text.strip().split('\n')

    # 找出末尾答案汇总行（全由 A-D 字母和空格组成）
    answer_line = ''
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if line and all(c in 'ABCD ' for c in line):
            answer_line = line
            break
    answers = answer_line.split()

    questions = []  # [(question_text, [option_texts])]
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.strip().startswith('分数'):
            i += 1
            while i < len(lines) and (lines[i].strip().startswith('作者') or lines[i].strip().startswith('单位')):
                i += 1

            # 收集题干行
            question_lines = []
            while i < len(lines):
                cur = lines[i]
                stripped = cur.strip()
                if re.match(r'^[A-D]\.\s*$', stripped):
                    break
                if stripped in META_LINES:
                    break
                if re.match(r'^\d+\s*分\s*$', stripped):
                    break
                if stripped:
                    question_lines.append(cur)
                i += 1

            non_empty_q = [q.rstrip() for q in question_lines if q.strip()]
            question_text = '\n'.join(non_empty_q)

            # 收集选项文本（选项标签单独一行：A. / B. / C. / D.）
            option_texts = []
            current_option_lines = []
            current_label = None

            while i < len(lines):
                cur = lines[i]
                stripped = cur.strip()

                if re.match(r'^[A-D]\.\s*$', stripped):
                    if current_label is not None and current_option_lines:
                        text = ' '.join(l.rstrip() for l in current_option_lines).strip()
                        option_texts.append(text)
                    current_label = stripped[0]
                    current_option_lines = []
                    i += 1
                    continue

                if stripped in META_LINES or re.match(r'^\d+\s*分\s*$', stripped) or stripped.startswith('分数'):
                    break

                if stripped:
                    current_option_lines.append(cur)
                i += 1

            if current_label is not None and current_option_lines:
                text = ' '.join(l.rstrip() for l in current_option_lines).strip()
                option_texts.append(text)

            questions.append((question_text, option_texts))

            # 跳过剩余元信息直到下一个题目
            while i < len(lines):
                cur = lines[i].strip()
                if cur in META_LINES or re.match(r'^\d+\s*分\s*$', cur):
                    i += 1
                elif cur.startswith('分数'):
                    break
                else:
                    i += 1
                    break
            continue
        i += 1

    records = []
    for idx, (qt, opts) in enumerate(questions):
        raw = answers[idx] if idx < len(answers) else None
        records.append({"text": qt, "options": opts, "raw_answer": raw})
    return records


def parse(text):
    """解析为可入库的选择题对象（单选/多选），无有效答案或选项的跳过"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # 兼容 Windows 换行
    qs = []
    for r in _scan(text):
        q = _letters_to_choice(r["text"], r["options"], r["raw_answer"])
        if q is not None:
            qs.append(q)
    return qs


def render(questions):
    """生成 text_converted 排版：题干 / 空行 / 选项文本每行一个 / 空行 / 答案"""
    out = []
    for q in questions:
        out.append(q.text)
        out.append('')
        for _, opt in (q.options or []):
            out.append(opt)
        out.append('')
        out.append(q.answer)
    return '\n'.join(out)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    records = _scan(content)
    print(f'找到 {len(records)} 个题目')
    for idx, r in enumerate(records):
        preview = r["text"][:50].replace('\n', '\\n')
        print(f'  [{idx}] {preview}... ({len(r["options"])} 选项) -> {r["raw_answer"]}')
    questions = parse(content)
    print(f'可导入 {len(questions)} 道（跳过无有效答案/选项的 {len(records) - len(questions)} 道）')
    output = render(questions)
    with open(os.path.join(BASE, 'text_converted.txt'), 'w', encoding='utf-8') as f:
        f.write(output)
    print(f'\n总行数: {len(output.split(chr(10)))}')
    print('\n--- 转换结果预览（前20行）---')
    for li, line in enumerate(output.split('\n')[:20], 1):
        print(f'{li:3d}| {repr(line)}')


if __name__ == '__main__':
    main()
