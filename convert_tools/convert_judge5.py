# -*- coding: utf-8 -*-
"""judge5 · 简答题（纯文本格式，答案以空行与题干/下一题分隔）

可接受格式：
    题干1

    参考答案1（可多行）

    题干2

    参考答案2
    …

题干块与答案块各以空行分隔。产出 简答题（不自动判分，作答后由用户自评）。

作为 convert_tools 的 judge 插件使用（文件名即 id）；也可直接运行。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models.question import EssayQuestion  # noqa: E402
from convert_tools._plain_common import normalize_lines, read_block  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_NAME = "简答题"
JUDGE_ORDER = 70
JUDGE_DESC = "简答题（纯文本）：题干/空行/参考答案(可多行，以空行结束)"


def parse(text):
    lines = normalize_lines(text)
    qs = []
    i = 0
    while True:
        stem, i = read_block(lines, i)
        if not stem:
            break
        ans, i = read_block(lines, i)  # 答案块：读到空行为止（可多行）
        if not ans:
            continue
        qs.append(EssayQuestion(text="\n".join(stem), answer="\n".join(ans)))
    return qs


def render(questions):
    out = []
    for q in questions:
        out.append(q.text)
        out.append('')
        out.append(q.answer)
        out.append('')
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    qs = parse(content)
    print(f'识别到 {len(qs)} 道简答题')
    for idx, q in enumerate(qs):
        print(f'  [{idx}] {q.text[:50].replace(chr(10), "\\n")}...')


if __name__ == '__main__':
    main()
