# -*- coding: utf-8 -*-
"""转换判断题 v2：从每道题的"参考答案"行读取答案。

作为 convert_tools 的 judge 插件使用（文件名即 id/名字）；
也可直接运行：读取本目录 text.txt，把转换结果写入本目录 text_converted.txt。
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models.question import TrueFalseQuestion  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_DESC = "判断题：从每题下方的“参考答案”行读取答案"

_TF2ANS = {"T": "正确", "F": "错误"}
_ANS2TF = {"正确": "T", "错误": "F"}


def _scan(text):
    """复刻原转换解析，返回 [(question_text, raw_answer)]，无答案的不返回"""
    lines = text.strip().split('\n')
    questions = []  # 每项: (question_text, answer T/F)
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.strip().startswith('分数'):
            i += 1  # 跳过分数字
            while i < len(lines) and (lines[i].strip().startswith('作者') or lines[i].strip().startswith('单位')):
                i += 1

            question_lines = []
            answer = None
            while i < len(lines):
                cur = lines[i]
                if not cur.strip():
                    if i + 1 < len(lines) and lines[i + 1].strip() in ('T', 'F', '参考答案'):
                        break  # 题干结束
                    i += 1
                elif cur.strip() in ('T', 'F'):
                    break
                elif cur.strip() == '参考答案':
                    break
                elif cur.strip() in ('评测结果', '答案正确', '答案错误', '得分'):
                    break
                elif re.match(r'^\d+\s*分\s*$', cur.strip()):
                    break
                else:
                    question_lines.append(cur)
                    i += 1

            non_empty = [q.rstrip() for q in question_lines if q.strip()]
            question_text = '\n'.join(non_empty)

            # 查找参考答案（跳过 T/F 行、元信息行等）
            while i < len(lines):
                cur = lines[i].strip()
                if cur == '参考答案':
                    if i + 1 < len(lines) and lines[i + 1].strip() in ('T', 'F'):
                        answer = lines[i + 1].strip()
                        i += 2
                    else:
                        i += 1
                    break
                elif cur in ('T', 'F'):
                    i += 1
                elif cur in ('评测结果', '答案正确', '答案错误', '得分'):
                    i += 1
                elif re.match(r'^\d+\s*分\s*$', cur):
                    i += 1
                else:
                    i += 1
                    if cur and not cur.startswith('分数'):
                        break

            if answer:
                questions.append((question_text, answer))
        else:
            i += 1

    return questions


def parse(text):
    """解析为可入库的判断题对象"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # 兼容 Windows 换行
    qs = []
    for qt, raw in _scan(text):
        ans = _TF2ANS.get(raw.strip().upper())
        if not qt.strip() or not ans:
            continue
        qs.append(TrueFalseQuestion(text=qt, answer=ans))
    return qs


def render(questions):
    """生成 text_converted 排版：题干 / 空行 / 答案(T或F)"""
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
    for idx, (q_text, ans) in enumerate(records):
        preview = q_text[:60].replace('\n', '\\n')
        print(f'  [{idx}] {preview}... -> {ans}')
    questions = parse(content)
    output = render(questions)
    with open(os.path.join(BASE, 'text_converted.txt'), 'w', encoding='utf-8') as f:
        f.write(output)
    print(f'\n总行数: {len(output.split(chr(10)))}')
    print('\n--- 转换结果预览（前20行）---')
    for li, line in enumerate(output.split('\n')[:20], 1):
        print(f'{li:3d}| {repr(line)}')


if __name__ == '__main__':
    main()
