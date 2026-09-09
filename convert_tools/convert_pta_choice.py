# -*- coding: utf-8 -*-
"""PTA 选择题（原 convert_judge4，已覆盖原 convert_judge3 的能力）

可接受文本（拼题A/PTA 平台导出的选择题）：分数/作者/单位 题块；
优先从每题“参考答案”行读取答案，没有则用末尾字母汇总行（A-Z）。
选项支持 “A. 文本同在一行” 与 “A.” 单独一行再跟多行选项文本。

作为 convert_tools 的 judge 插件使用（文件名即 id）；
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
JUDGE_NAME = "PTA选择题"
JUDGE_ORDER = 20
JUDGE_DESC = "选择题（PTA）：优先读每题“参考答案”行，没有则用末尾字母汇总行"

META_LINES = {'评测结果', '答案正确', '答案错误', '得分'}
OPTION_PATTERN = re.compile(r'^[A-Z]\.')


def _letters_to_choice(text, option_texts, raw_answer):
    """按答案字母构建单选/多选题对象；无法构建返回 None"""
    letters = re.sub(r'[^A-Za-z]', '', raw_answer or "").upper()
    if not text.strip() or not option_texts or not letters:
        return None
    if len(option_texts) > 26:
        return None  # 选项数超过 A-Z 可表达范围，跳过（多为格式误判）
    options = [("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i], t) for i, t in enumerate(option_texts)]
    if len(letters) >= 2:
        return ChoiceQuestion(
            text=text, options=options, answer=letters, choice_type="multiple",
            multiple_answers=list(letters),
        )
    return ChoiceQuestion(
        text=text, options=options, answer=letters[0], choice_type="single",
        multiple_answers=None,
    )


def _scan(text):
    """复刻原转换解析，返回 [(question_text, [option_texts], raw_answer|None)]"""
    lines = text.strip().split('\n')

    has_cankaodaan = any('参考答案' in l for l in lines)

    # 备用答案：末尾字母汇总行
    fallback_answers = []
    if not has_cankaodaan:
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if stripped and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ ' for c in stripped):
                fallback_answers = stripped.split()
                break

    questions = []
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
                if OPTION_PATTERN.match(stripped):
                    break
                if stripped in META_LINES:
                    break
                if re.match(r'^\d+\s*分\s*$', stripped):
                    break
                if stripped == '参考答案':
                    break
                if stripped:
                    question_lines.append(cur)
                i += 1

            non_empty_q = [q.rstrip() for q in question_lines if q.strip()]
            question_text = '\n'.join(non_empty_q)

            # 收集选项文本（支持 "A. 文本同在一行" 与 "A." 标签另起一行的多行文本）
            option_texts = []
            current_option_lines = []
            current_label = None

            while i < len(lines):
                cur = lines[i]
                stripped = cur.strip()

                if OPTION_PATTERN.match(stripped):
                    if current_label is not None:
                        if current_option_lines:
                            text = ' '.join(l.rstrip() for l in current_option_lines).strip()
                        else:
                            text = ''
                        option_texts.append(text)
                    rest = stripped[2:].strip()
                    current_label = stripped[0]
                    current_option_lines = []
                    if rest:
                        current_option_lines.append(rest)
                    i += 1
                    continue

                if stripped in META_LINES or re.match(r'^\d+\s*分\s*$', stripped) or stripped.startswith('分数') or stripped == '参考答案':
                    break

                if stripped:
                    current_option_lines.append(cur)
                i += 1

            if current_label is not None:
                if current_option_lines:
                    text = ' '.join(l.rstrip() for l in current_option_lines).strip()
                else:
                    text = ''
                option_texts.append(text)

            # 查找“参考答案”
            answer = None
            while i < len(lines):
                cur = lines[i].strip()
                if cur == '参考答案':
                    if i + 1 < len(lines) and lines[i + 1].strip():
                        answer = lines[i + 1].strip()
                        i += 2
                    else:
                        i += 1
                    break
                elif cur in META_LINES or re.match(r'^\d+\s*分\s*$', cur):
                    i += 1
                elif cur.startswith('分数'):
                    break
                else:
                    i += 1

            # 无“参考答案”则用末尾汇总行的备用答案
            if answer is None and fallback_answers and len(questions) < len(fallback_answers):
                answer = fallback_answers[len(questions)]

            questions.append((question_text, option_texts, answer))
            continue
        i += 1

    return questions


def parse(text):
    """解析为可入库的选择题对象，无有效答案/选项的跳过"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # 兼容 Windows 换行
    qs = []
    for qt, opts, raw in _scan(text):
        q = _letters_to_choice(qt, opts, raw)
        if q is not None:
            qs.append(q)
    return qs


def render(questions):
    """生成 text_converted 排版（连续空行去重，与旧版一致）"""
    raw_out = []
    for q in questions:
        raw_out.append(q.text)
        raw_out.append('')
        for _, opt in (q.options or []):
            raw_out.append(opt)
        raw_out.append('')
        raw_out.append(q.answer)

    final_lines = []
    prev_empty = False
    for line in raw_out:
        if line == '':
            if not prev_empty:
                final_lines.append(line)
                prev_empty = True
        else:
            final_lines.append(line)
            prev_empty = False
    return '\n'.join(final_lines)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    records = _scan(content)
    print(f'找到 {len(records)} 个题目')
    for idx, (q, opts, ans) in enumerate(records):
        preview = q[:50].replace('\n', '\\n')
        print(f'  [{idx}] {preview}... ({len(opts)} 选项) -> {ans}')
    questions = parse(content)
    print(f'可导入 {len(questions)} 道（跳过无有效答案/选项的 {len(records) - len(questions)} 道）')
    output = render(questions)
    with open(os.path.join(BASE, 'text_converted.txt'), 'w', encoding='utf-8') as f:
        f.write(output)
    print(f'\n总行数: {len(output.split(chr(10)))}')


if __name__ == '__main__':
    main()
