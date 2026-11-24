# -*- coding: utf-8 -*-
"""自检：文件导入解析（Word / Excel / CSV / TSV / Markdown / TXT）。

运行：python file_import_selftest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from file_import import parse_file, parse_text  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


def ans_of(d):
    a = d.get("answer")
    if isinstance(a, dict):
        return " ".join(x["accept"][0] for x in a.get("items") or [])
    return str(a or "")


# ---------- 1) 纯文本规则 ----------
t1 = """(单选题,1.0分) 以太网采用的发送策略是（）。
A. 站点可随时发送
B. 先侦听，信道空闲时发送
C. 采用 CSMA/CD 协议发送
D. 以上都不对
我的答案:D 正确答案: C
(判断题,1.0分) 交换机可以隔离冲突域。
我的答案:对 正确答案: 对
"""
ds = parse_text(t1)
check("纯文本：识别单选+判断", len(ds) == 2 and ds[0]["type"] == "单选题" and ds[1]["type"] == "判断题", ds)
check("纯文本：取「正确答案」而不是「我的答案」", ds and ans_of(ds[0]) == "C", ds and ans_of(ds[0]))
check("纯文本：去掉「(单选题,1.0分)」标记", ds and "(单选题" not in ds[0]["text"], ds and ds[0]["text"])
check("纯文本：判断题答案为正确", ds and ds[1].get("answer") == "正确", ds and ds[1].get("answer"))

t2 = """毛泽东思想作为党的指导思想写进党章是在（） A. 党的七大 B. 党的六届七中全会 C. 党的七届二中全会 D. 党的五大 答案：A
排列34521是（  ）排列。
答案：奇
什么是中断方式？
答案：CPU 暂停现行程序，转去处理紧急事件。
"""
ds2 = parse_text(t2)
types = [d["type"] for d in ds2]
check("纯文本：题干与答案同段也能切", len(ds2) == 3 and types == ["单选题", "填空题", "简答题"], types)
check("纯文本：填空题把（ ）换成【1】", "【1】" in ds2[1]["text"] and ans_of(ds2[1]) == "奇", ds2[1])
check("纯文本：简答题保留长答案", len(ans_of(ds2[2])) > 10, ans_of(ds2[2]))

# ---------- 2) CSV ----------
csv_text = "题型,题干,选项,答案\n判断题,线性无关的向量组中不含零向量。,,正确\n单选题,矩阵可逆的充要条件是（）,A.|A|=0|B.|A|≠0|C.A 方阵|D.A 对称,B\n"
res = parse_file("a.csv", csv_text.encode("utf-8"), "测试")
check("CSV：表头映射出 2 道", res["stats"]["total"] == 2, res["stats"])
check("CSV：选项列用 | 分隔也能拆", res["drafts"][1]["type"] == "单选题"
      and len(res["drafts"][1]["options"]) == 4 and ans_of(res["drafts"][1]) == "B", res["drafts"][1])

# ---------- 3) TSV ----------
tsv = "题型\t题干\t答案\n判断题\t两个向量组等价则秩相等。\t正确\n"
res = parse_file("a.tsv", tsv.encode("utf-8"), "测试")
check("TSV：解析 1 道判断题", res["stats"]["total"] == 1 and res["drafts"][0]["type"] == "判断题", res["stats"])

# ---------- 4) Markdown 管道表格 ----------
md = """# 题库

| 题型 | 题干 | 选项 | 答案 |
| --- | --- | --- | --- |
| 判断题 | 两个向量组等价则秩相等。 | | 正确 |
| 单选题 | 线性相关的充要条件是（） | A.含零向量|B.存在不全为零的组合|C.秩小于n|D.以上都对 | B |
"""
res = parse_file("a.md", md.encode("utf-8"), "测试")
check("Markdown：表格识别 2 道", res["stats"]["total"] == 2, res["stats"])
check("Markdown：单元格内含 | 的选项也能拆", res["drafts"][1]["type"] == "单选题"
      and len(res["drafts"][1]["options"]) == 4, res["drafts"][1] if res["drafts"] else None)

# ---------- 5) TXT ----------
res = parse_file("a.txt", t1.encode("gb18030"), "测试")
check("TXT：GB18030 编码也能读", res["stats"]["total"] == 2, res["stats"])

# ---------- 6) Excel ----------
xlsx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "sample.xlsx")
if os.path.exists(xlsx_path):
    res = parse_file("sample.xlsx", open(xlsx_path, "rb").read(), "测试")
    check("XLSX：表头映射 2 道", res["stats"]["total"] == 2, res["stats"])
    check("XLSX：答案正确", any(ans_of(d) == "B" for d in res["drafts"]), res["drafts"])

# ---------- 7) Word（段落 + 表格 + 内嵌图片）----------
docx_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "sample.docx")
if os.path.exists(docx_path):
    res = parse_file("sample.docx", open(docx_path, "rb").read(), "测试")
    check("DOCX：段落+表格共 5 道", res["stats"]["total"] == 5, res["stats"])
    check("DOCX：表格题也被识别", any(d["type"] == "判断题" and "中断" in d["text"] for d in res["drafts"]),
          [d["text"] for d in res["drafts"]])
    check("DOCX：内嵌图片被提取", len(res["images"]) == 1, [i["name"] for i in res["images"]])
    check("DOCX：图片位置替换成 [科目/文件名] token",
          any("[测试/" in d["text"] for d in res["drafts"]),
          [d["text"] for d in res["drafts"]])

# ---------- 8) 不支持的类型 ----------
try:
    parse_file("a.pdf", b"%PDF", "测试")
    check("PDF：应当报错", False)
except ValueError as e:
    check("PDF：应当报错", "不支持" in str(e), str(e))

print("\n" + ("文件导入自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
sys.exit(1 if fails else 0)
