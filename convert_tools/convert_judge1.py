# -*- coding: utf-8 -*-
"""转换判断题 v1：末尾行读取答案。

作为 convert_tools 的 judge 插件使用（文件名即 id/名字）；
也可直接运行：读取本目录 text.txt，把转换结果写入本目录 text_converted.txt。
"""
import os
import re  # noqa: F401  (保留 re，风格与旧脚本一致)
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models.question import TrueFalseQuestion  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_DESC = "判断题：从文件末尾的 T/F 答案行读取答案"

_TF2ANS = {"T": "正确", "F": "错误"}
_ANS2TF = {"正确": "T", "错误": "F"}


def _scan(text):
    """复刻原转换解析，返回 [{text, raw_answer}]，raw_answer 为 'T'/'F' 或 None"""
    lines = text.strip().split('\n')

    # 找出答案汇总行（最后一行，全由 T/F/空格 组成）
    answer_line = ''
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if line and all(c in 'TF ' for c in line):
            answer_line = line
            break
    answers = answer_line.split()

    questions = []  # 题目文本列表（与答案按序对应）
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        # 检测题目块开头：分数
        if line.strip().startswith('分数'):
            i += 1
            # 跳过 分数 2, 作者 xxx, 单位 xxx
            while i < len(lines) and (lines[i].strip().startswith('作者') or lines[i].strip().startswith('单位')):
                i += 1
            question_lines = []
            while i < len(lines):
                cur = lines[i]
                if not cur.strip():
                    # 空行且下一行是 T → 题干结束
                    if i + 1 < len(lines) and lines[i + 1].strip() == 'T':
                        break
                    i += 1
                elif cur.strip() in ('T', 'F'):
                    break
                elif cur.strip() in ('评测结果', '答案正确', '答案错误', '得分') or cur.strip() in ('2 分',):
                    break
                else:
                    question_lines.append(cur)
                    i += 1

            question_text = '\n'.join(q.rstrip() for q in question_lines).strip()
            if question_text:
                questions.append(question_text)

            # 跳过 T / F / 评测结果 / 答案正确 / 得分 / 2 分
            while i < len(lines) and lines[i].strip() in ('T', 'F'):
                i += 1
            while i < len(lines) and lines[i].strip() in ('评测结果', '答案正确', '答案错误', '得分', '2 分'):
                i += 1
            continue
        i += 1

    records = []
    for idx, qt in enumerate(questions):
        raw = answers[idx] if idx < len(answers) else None
        records.append({"text": qt, "raw_answer": raw})
    return records


def parse(text):
    """解析为可入库的判断题对象（无有效 T/F 答案的跳过）"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # 兼容 Windows 换行
    qs = []
    for r in _scan(text):
        raw = (r["raw_answer"] or "").strip().upper()
        ans = _TF2ANS.get(raw)
        if not r["text"].strip() or not ans:
            continue
        qs.append(TrueFalseQuestion(text=r["text"], answer=ans))
    return qs


def render(questions):
    """生成 text_converted 排版：题干 / 空行 / 答案(T或F)（答案后不空行）"""
    out = []
    for q in questions:
        out.append(q.text)
        out.append('')
        out.append(_ANS2TF.get(q.answer, q.answer))
    return '\n'.join(out)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    records = _scan(content)
    print(f'找到 {len(records)} 个题目')
    for idx, r in enumerate(records):
        preview = r["text"][:60].replace('\n', '\\n')
        print(f'  [{idx}] {preview}... -> {r["raw_answer"]}')
    questions = parse(content)
    print(f'可导入 {len(questions)} 道（跳过无有效答案 {len(records) - len(questions)} 道）')
    output = render(questions)
    with open(os.path.join(BASE, 'text_converted.txt'), 'w', encoding='utf-8') as f:
        f.write(output)
    print(f'\n总行数: {len(output.split(chr(10)))}')
    print('\n--- 转换结果预览（前20行）---')
    for li, line in enumerate(output.split('\n')[:20], 1):
        print(f'{li:3d}| {repr(line)}')


if __name__ == '__main__':
    main()
