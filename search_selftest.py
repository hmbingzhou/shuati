# -*- coding: utf-8 -*-
"""自检：题库搜索支持多行题干 / 忽略空白与大小写。

运行：python search_selftest.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from question_manager import norm_search_text, keyword_matches  # noqa: E402
import webui_server  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + (f"  {detail}" if detail is not None and not cond else ""))
    if not cond:
        fails.append(name)


# ---------- 1) 归一化 ----------
check("去空白并转小写", norm_search_text("  Hello\n\tWORLD  ") == "helloworld")
check("全角空格也去掉", norm_search_text("甲\u3000乙") == "甲乙")

# ---------- 2) 多行题干匹配 ----------
check("跨换行可用空格搜到", keyword_matches("第一行\n第二行", "第一行 第二行"))
check("跨换行且大小写不同也能搜到", keyword_matches("Hello\nWorld", "hello world"))
check("换行处直接连着打也命中", keyword_matches("第一行\n第二行", "第一行第二行"))
check("只出现在第二行也能命中", keyword_matches("第一行\n第二行", "第二行"))
check("不命中就是不命中", not keyword_matches("abc", "abd"))
check("空关键词不筛选", keyword_matches("任何内容", "") and keyword_matches("x", "   "))

# ---------- 3) 真实题库：多行题干端到端 ----------
picked = None
for p in sorted(__import__("glob").glob("data/*.json")):
    if os.path.basename(p) == "recycle_bin.json":
        continue
    d = json.load(open(p, encoding="utf-8"))
    for q in d if isinstance(d, list) else []:
        if isinstance(q, dict) and "\n" in str(q.get("text") or ""):
            picked = (os.path.basename(p)[:-5], q["text"])
            break
    if picked:
        break

check("题库里存在多行题干的题", picked is not None)
if picked:
    subj, text = picked
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) >= 2:
        # 用「第一行结尾 + 第二行开头」拼跨行关键词（不能截断行内内容，否则本就不是子串）
        kw = lines[0] + " " + lines[1]
        hit = webui_server.handle_questions({"subject": [subj], "keyword": [kw], "pageSize": ["5"]})
        found = any(q["text"] == text for q in hit["items"])
        check(f"跨行关键词能在接口里搜到（{subj}，{len(hit['items'])} 条）", found, kw)
    # 关键词里直接带换行也要能搜到
    kw_nl = lines[0] + "\n" + lines[1] if len(lines) >= 2 else ""
    if kw_nl:
        hit2 = webui_server.handle_questions({"subject": [subj], "keyword": [kw_nl], "pageSize": ["5"]})
        check("关键词里直接带换行也能搜到", any(q["text"] == text for q in hit2["items"]), kw_nl)

print("\n" + ("题库搜索自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
sys.exit(1 if fails else 0)
