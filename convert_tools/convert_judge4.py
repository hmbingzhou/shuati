# -*- coding: utf-8 -*-
"""judge4 · 填空题（题干内 [N] 标记 + 下方逐空答案行）

可接受格式：
    题干1题干1[1]题干1题干1[2]题干1题干1[3]题干1题干1

    [1]答案1
    [2]答案2
    [3]答案3
    题干2题干2[1]题干2题干2[2]题干2

    [1]答案1
    [2]答案2
    …

说明：
- 题干里的行内 [N] 是空位标记，按出现顺序自动转成 v2 规范标记 【1】【2】…；
- 空行之后连续出现的 [N]答案 行是各空的答案；
- 某空缺少答案时该空 accept 为空，导入后可在逐题编辑器补；
- 每个空支持一个答案；同一空的多个可接受答案/可换序请导入后在编辑器中设置。

作为 convert_tools 的 judge 插件使用（文件名即 id）；也可直接运行。
"""

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models.question import FillBlankQuestion  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_NAME = "填空题"
JUDGE_ORDER = 60
JUDGE_DESC = "填空题（纯文本）：题干内[N]空位，下方[1]答案行逐空给答案"

_ANS_LINE_RE = re.compile(r"^\s*\[\s*(\d+)\s*\]\s*(.*)$")
_MARK_RE = re.compile(r"\[\s*(\d+)\s*\]")


def _to_canonical(stem_text, num2ord=None):
    """把题干里行内 [N] 按出现顺序转成 【序号】；返回 (新文本, 序号->原编号映射, 空位数)"""
    if num2ord is None:
        num2ord = {}

    def _repl(m):
        num = int(m.group(1))
        if num not in num2ord:
            num2ord[num] = len(num2ord) + 1
        return f"【{num2ord[num]}】"

    new_text = _MARK_RE.sub(_repl, stem_text)
    return new_text, num2ord, len(num2ord)


def parse(text):
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n = len(lines)
    qs = []
    i = 0
    while i < n:
        # 题干块：收集非空、且不是 [N]答案 行的内容
        stem_lines = []
        while i < n and lines[i].strip() and not _ANS_LINE_RE.match(lines[i]):
            stem_lines.append(lines[i].rstrip())
            i += 1
        while i < n and not lines[i].strip():
            i += 1
        # 答案块
        ans_entries = {}
        while i < n:
            m = _ANS_LINE_RE.match(lines[i])
            if not m:
                break
            ans_entries[int(m.group(1))] = m.group(2).strip()
            i += 1
        while i < n and not lines[i].strip():
            i += 1  # 为下一题题干准备（题目之间可能无空行）

        stem_text = "\n".join(stem_lines).strip()
        if not stem_text:
            continue
        if "[" not in stem_text and not ans_entries:
            continue  # 既无空位也无答案，视为杂散文本
        num2ord = {}
        new_text, num2ord, _count = _to_canonical(stem_text, num2ord)
        items = []
        for num in sorted(num2ord, key=lambda k: num2ord[k]):
            val = ans_entries.get(num)
            items.append({"accept": [val]} if val else {"accept": []})
        # 答案行里存在题干未引用的编号 → 补成额外空位
        for num in sorted(ans_entries):
            if num not in num2ord:
                num2ord[num] = len(num2ord) + 1
                items.append({"accept": [ans_entries[num]]})
                new_text += f"【{num2ord[num]}】"
        if not items:
            continue
        qs.append(FillBlankQuestion(text=new_text, answer=items))
    return qs


def render(questions):
    out = []
    for q in questions:
        out.append(q.text)
        out.append('')
        items = getattr(q, "answer", []) or []
        for idx, it in enumerate(items, 1):
            acc = it.get("accept") or []
            out.append(f"[{idx}]" + (" / ".join(str(a) for a in acc) if acc else ""))
        out.append('')
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


def main():
    with open(os.path.join(BASE, 'text.txt'), 'r', encoding='utf-8') as f:
        content = f.read()
    qs = parse(content)
    print(f'识别到 {len(qs)} 道填空题')
    for idx, q in enumerate(qs):
        print(f'  [{idx}] {q.text[:60].replace(chr(10), "\\n")}... -> {q.answer_text()[:40]}')


if __name__ == '__main__':
    main()
