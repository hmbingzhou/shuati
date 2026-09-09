# -*- coding: utf-8 -*-
"""judge3 · 判断题（纯文本格式）

可接受格式（题干读到空行结束，其后一行是答案 token；答案行后可直接接下一题题干）：
    题干1

    正确
    题干2

    错误
    …

答案 token 接受：正确/错误/对/错/T/F/t/f/√/×/true/false/是/否，
由 TrueFalseQuestion 统一归一为 正确/错误；无法识别则跳过该题。

作为 convert_tools 的 judge 插件使用（文件名即 id）；也可直接运行。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from convert_tools._plain_common import (  # noqa: E402
    normalize_lines, read_block, skip_blank, make_tf,
)

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_NAME = "判断题"
JUDGE_ORDER = 50
JUDGE_DESC = "判断题（纯文本）：题干/空行/答案行（正确/错误/T/F/对/错）"


def parse(text):
    lines = normalize_lines(text)
    qs = []
    i = 0
    n = len(lines)
    while True:
        stem, i = read_block(lines, i)
        if not stem:
            break
        i = skip_blank(lines, i)
        if i >= n:
            break
        ans_token = lines[i].strip()
        i += 1
        q = make_tf("\n".join(stem), ans_token)
        if q is not None:
            qs.append(q)
    return qs


def render(questions):
    out = []
    for q in questions:
        out.append(q.text)
        out.append('')
        out.append('正确' if q.answer == '正确' else '错误')
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    qs = parse(content)
    print(f'识别到 {len(qs)} 道判断题')
    for idx, q in enumerate(qs):
        print(f'  [{idx}] {q.text[:50].replace(chr(10), "\\n")}... -> {q.answer}')


if __name__ == '__main__':
    main()
