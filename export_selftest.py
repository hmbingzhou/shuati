# -*- coding: utf-8 -*-
"""自检：导出（题库 / 试卷 / 错题本）。

只测生成逻辑，不启动服务。
运行：python export_selftest.py
"""
import base64
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".probe_export_selftest")
shutil.rmtree(HOME, ignore_errors=True)
PICS = os.path.join(HOME, "pictures")
os.makedirs(os.path.join(PICS, "测试"), exist_ok=True)

# 1x1 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
with open(os.path.join(PICS, "测试", "fig1.png"), "wb") as f:
    f.write(PNG)

import exporter  # noqa: E402
from models.question import Question  # noqa: E402

exporter.set_pictures_dir(PICS)

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


QS = [
    Question.from_dict({"type": "单选题", "subject": "测试", "text": "下列哪个是总线？",
                        "options": [["A", "数据总线"], ["B", "硬盘"], ["C", "内存"], ["D", "CPU"]],
                        "answer": "A"}),
    Question.from_dict({"type": "判断题", "subject": "测试", "text": "中断方式具有随机性。", "answer": "正确"}),
    Question.from_dict({"type": "简答题", "subject": "测试",
                        "text": "如图所示的电路功能是什么？ [测试/fig1.png]", "answer": "与非门"}),
]

# ---------- 题库 HTML ----------
data, name, ctype = exporter.export_bank("测试", QS, "html", with_answers=True)
html = data.decode("utf-8")
check("HTML 文件名带科目与时间戳", name.startswith("测试_题库_") and name.endswith(".html"), name)
check("HTML content-type 正确", ctype.startswith("text/html"), ctype)
check("HTML 含标题与题数", "测试 · 题库" in html and "共 3 题" in html, html[:200])
check("HTML 含题干", "下列哪个是总线" in html)
check("HTML 含选项", "<b>A.</b>" in html and "数据总线" in html)
check("HTML 含答案块", 'class="ans"' in html and "与非门" in html)
check("HTML 图片内嵌为 base64", "data:image/png;base64," in html)
check("HTML 无缺失图片告警", "图片缺失" not in html)
check("HTML 有打印样式", "@page" in html and "break-inside" in html)

# ---------- 题库 Markdown ----------
data, name, ctype = exporter.export_bank("测试", QS, "md", with_answers=True)
md = data.decode("utf-8")
check("MD 文件名正确", name.startswith("测试_题库_") and name.endswith(".md"), name)
check("MD 首行是标题", md.splitlines()[0] == "# 测试 · 题库", md.splitlines()[0])
check("MD 含题型标记", "**1. [单选题]**" in md)
check("MD 含选项列表", "- **A.** 数据总线" in md)
check("MD 含答案", "**答案：** A" in md or "**答案：** 与非门" in md)

# ---------- 学生版 ----------
data, _, _ = exporter.export_bank("测试", QS, "html", with_answers=False)
html2 = data.decode("utf-8")
check("学生版不含答案块", 'class="ans"' not in html2)
check("学生版简答题留答题区", 'class="answer-lines"' in html2)
check("学生版标注「不含答案」", "不含答案" in html2)

# ---------- 试卷 ----------
data, name, _ = exporter.export_paper("测试", QS, "html", with_answers=True, note="20 题 / 60 分钟")
html3 = data.decode("utf-8")
check("试卷教师版文件名", "试卷_教师版" in name, name)
check("试卷教师版含答案", 'class="ans"' in html3 and "教师版" in html3)
check("试卷带备注信息", "20 题 / 60 分钟" in html3)

data, name, _ = exporter.export_paper("测试", QS, "html", with_answers=False)
check("试卷学生版文件名", "试卷_学生版" in name, name)
check("试卷学生版无答案", 'class="ans"' not in data.decode("utf-8"))

# ---------- 错题本 ----------
data, name, _ = exporter.export_wrong(QS[:2], "html", True, "错题本")
html4 = data.decode("utf-8")
check("错题本文件名", name.startswith("错题本_"), name)
check("错题本含两道题", "下列哪个是总线" in html4 and "中断方式具有随机性" in html4)

# ---------- 图片缺失时的降级 ----------
QS2 = [Question.from_dict({"type": "简答题", "subject": "测试", "text": "看图 [测试/nothere.png]", "answer": "x"})]
data, _, _ = exporter.export_bank("测试", QS2, "html", with_answers=True)
check("图片缺失时给占位提示", "图片缺失" in data.decode("utf-8"))

# ---------- 文件名清理 ----------
data, name, _ = exporter.export_bank('a/b:c*?"<>|', QS, "md", True)
check("文件名里的非法字符被替换", "/" not in name and ":" not in name and "*" not in name, name)

# ---------- 空题库 ----------
data, name, _ = exporter.export_bank("空", [], "html", True)
check("空题库也能导出（0 题）", "共 0 题" in data.decode("utf-8"))

shutil.rmtree(HOME, ignore_errors=True)
print("\n" + ("导出自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
sys.exit(1 if fails else 0)
