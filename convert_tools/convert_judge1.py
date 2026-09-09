# -*- coding: utf-8 -*-
"""judge1 · 单选题（纯文本格式，答案为一个字母）

可接受格式（题干 / 空行 / 选项 / 空行 / 答案字母；答案行后可直接接下一题题干）：
    题干1

    选项一
    选项二
    …

    A
    题干2
    …

规则：题干读到空行结束，随后选项逐行（读到空行），再往后的一行是答案。
judge1 只接受【单个】字母答案；答案含 2 个及以上字母（多选数据）时该题跳过，
请改用 judge2（多选题）。

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
JUDGE_NAME = "单选题"
JUDGE_ORDER = 30
JUDGE_DESC = "单选题（纯文本）：题干/空行/选项/空行/单个字母答案行"


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
            continue  # 没有选项，可能是下一题题干被误读，直接跳过本段
        i = skip_blank(lines, i)
        if i >= n:
            break
        ans_line = lines[i].strip()
        i += 1
        letters = letters_of(ans_line)
        if len(letters) != 1:
            continue  # 非单选：跳过（多选请用 judge2）
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
    print(f'识别到 {len(qs)} 道单选题')
    for idx, q in enumerate(qs):
        print(f'  [{idx}] {q.text[:50].replace(chr(10), "\\n")}... -> {q.answer}')


if __name__ == '__main__':
    main()
