# -*- coding: utf-8 -*-
"""PTA 判断题（原 convert_judge2 + 合并 convert_judge1）

可接受文本（拼题A/PTA 平台导出的判断题）：
    分数：N
    作者：…
    单位：…
    题干…（可多行）

    T / F            ← 或「参考答案」行下方跟 T/F

答案解析优先级：
    1. 每题下方若有「参考答案」行 → 用其 T/F；
    2. 全文没有「参考答案」时 → 用文件末尾的 T/F 汇总行（逐题按序对应）。
答案归一化：T/F/对/错/√/×/正确/错误 → TrueFalseQuestion 统一为 正确/错误。

作为 convert_tools 的 judge 插件使用（文件名即 id）；也可直接运行：
读取本目录 text.txt，把转换结果写入本目录 text_converted.txt。
"""

import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from models.question import TrueFalseQuestion  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_NAME = "PTA判断题"
JUDGE_ORDER = 10
JUDGE_DESC = "判断题（PTA）：优先读每题“参考答案”行，没有则用文件末尾 T/F 汇总行"

_TF2ANS = {"T": "正确", "F": "错误"}
_ANS2TF = {"正确": "T", "错误": "F"}
_META = {"评测结果", "答案正确", "答案错误", "得分"}
_DIGIT_DIV_RE = re.compile(r"^\d+\s*分\s*$")


def _split_lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _trailing_tf_summary(lines):
    """文件末尾的 T/F 汇总行（最后一行为全 T/F/空格组成）"""
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if s and all(c in "TFtf " for c in s):
            return [c.upper() for c in s if c in "TFtf"]
    return []


def _scan(text):
    """
    返回 [(question_text, answer 'T'/'F')]，解析不出答案的不返回。
    参考答案优先；全文无参考答案时用末尾 T/F 汇总行按序兜底。
    """
    lines = _split_lines(text)
    has_ref = any("参考答案" in l for l in lines)
    fallback = [] if has_ref else _trailing_tf_summary(lines)

    questions = []
    qidx = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if not line.strip().startswith("分数"):
            i += 1
            continue

        i += 1  # 跳过分数字
        while i < n and (lines[i].strip().startswith("作者") or lines[i].strip().startswith("单位")):
            i += 1

        # 收集题干
        q_lines = []
        while i < n:
            cur = lines[i]
            s = cur.strip()
            if not s:
                # 空行：若下一行是 T/F/参考答案 或元信息则视为题干结束
                if i + 1 < n and (lines[i + 1].strip() in ("T", "F", "参考答案")
                                  or lines[i + 1].strip() in _META
                                  or _DIGIT_DIV_RE.match(lines[i + 1].strip())):
                    break
                i += 1
                continue
            if s in ("T", "F") or s == "参考答案" or s in _META or _DIGIT_DIV_RE.match(s):
                break
            q_lines.append(cur)
            i += 1

        qt = "\n".join(l.rstrip() for l in q_lines).strip()

        # 查找参考答案（跳过中间的 T/F、元信息、数字分行）
        answer = None
        while i < n:
            s = lines[i].strip()
            if s == "参考答案":
                if i + 1 < n and lines[i + 1].strip().upper() in ("T", "F"):
                    answer = lines[i + 1].strip()
                    i += 2
                else:
                    i += 1
                break
            if s in ("T", "F") or s in _META or _DIGIT_DIV_RE.match(s):
                i += 1
                continue
            if s.startswith("分数"):
                break
            i += 1

        if answer is None and not has_ref and qidx < len(fallback):
            answer = fallback[qidx]
        qidx += 1

        if qt and answer:
            questions.append((qt, answer))
    return questions


def parse(text):
    """解析为可入库的判断题对象"""
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
    for idx, (qt, ans) in enumerate(records):
        print(f'  [{idx}] {qt[:60].replace(chr(10), "\\n")}... -> {ans}')
    questions = parse(content)
    print(f'可导入 {len(questions)} 道（跳过无有效答案 {len(records) - len(questions)} 道）')
    output = render(questions)
    with open(os.path.join(BASE, 'text_converted.txt'), 'w', encoding='utf-8') as f:
        f.write(output)
    print(f'\n总行数: {len(output.splitlines())}')


if __name__ == '__main__':
    main()
