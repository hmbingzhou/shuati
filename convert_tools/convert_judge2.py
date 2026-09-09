# -*- coding: utf-8 -*-
"""judge2 · 多选题（纯文本格式，答案为 2 个及以上不同字母）

可接受格式与 judge1（单选）相同：
    题干1

    选项一
    选项二
    …

    A C
    题干2
    …

judge2 只接受【≥2 个且不重复】的字母答案；单个字母的题（单选数据）请改用 judge1。

作为 convert_tools 的 judge 插件使用（文件名即 id）；也可直接运行。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from convert_tools._plain_common import (  # noqa: E402
    normalize_lines, read_block, skip_blank, letters_of, make_choice,
)

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_NAME = "多选题"
JUDGE_ORDER = 40
JUDGE_DESC = "多选题（纯文本）：题干/空行/选项/空行/多个字母答案行"


def parse(text):
    lines = normalize_lines(text)
    qs = []
    i = 0
    n = len(lines)
    while True:
        stem, i = read_block(lines, i)
        if not stem:
            break
        opts, i = read_block(lines, i)
        if not opts:
            continue
        i = skip_blank(lines, i)
        if i >= n:
            break
        ans_line = lines[i].strip()
        i += 1
        letters = letters_of(ans_line)
        if len(letters) < 2 or len(set(letters)) != len(letters):
            continue  # 不是多选答案：跳过（单选请用 judge1）
        q = make_choice("\n".join(stem), opts, letters)
        if q is not None:
            qs.append(q)
    return qs


def render(questions):
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
    qs = parse(content)
    print(f'识别到 {len(qs)} 道多选题')
    for idx, q in enumerate(qs):
        print(f'  [{idx}] {q.text[:50].replace(chr(10), "\\n")}... -> {q.answer}')


if __name__ == '__main__':
    main()
