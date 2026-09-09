# -*- coding: utf-8 -*-
"""v2 题目模型自检：六题型判分矩阵 + 序列化往返 + v1 旧格式读取。python question_v2_selftest.py"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from models.question import (  # noqa: E402
    Question, SingleChoiceQuestion, MultipleChoiceQuestion, TrueFalseQuestion,
    FillBlankQuestion, EssayQuestion, CalculationQuestion, ChoiceQuestion, collect_image_tokens,
)

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"[ok] {name}")
    else:
        fails.append(name)
        print(f"[FAIL] {name}  {detail}")


def q1(text, answer, **kw):
    return SingleChoiceQuestion(text, [["A", "甲"], ["B", "乙"]], answer, **kw)


def rt(q):
    """to_dict -> from_dict -> to_dict 往返一致性"""
    d1 = q.to_dict()
    q2 = Question.from_dict(d1)
    d2 = q2.to_dict()
    return d1 == d2, d1, d2


# ---- 单选 ----
s = q1("单选一题", "B", subject="Java")
ok, d1, d2 = rt(s)
check("单选 往返一致", ok, (d1, d2))
check("单选 options 序列化", d1.get("options") == [["A", "甲"], ["B", "乙"]] and s.choice_type == "single", d1)
check("单选 type", d1["type"] == "单选题")
check("单选 判分", s.check_answer("B") and s.check_answer("b") and not s.check_answer("A"))
check("单选 images 空", d1["images"] == [])

# ---- 多选 ----
m = MultipleChoiceQuestion("多选", [["A", "1"], ["B", "2"], ["C", "3"]], "AC", subject="Java")
ok, d1, d2 = rt(m)
check("多选 往返一致", ok)
check("多选 choice_type/label", m.choice_type == "multiple" and m.get_type_label() == "多选题")
check("多选 判分(全对/顺序/大小写)", m.check_answer("AC") and m.check_answer("ca") and not m.check_answer("AB") and not m.check_answer("A"))
check("多选 非法字母", not m.check_answer("ACE"))

# ---- 判断 ----
t = TrueFalseQuestion("判断", "√", subject="Java")
ok, d1, _ = rt(t)
check("判断 往返一致", ok)
check("判断 答案归一为正确", t.answer == "正确" and d1["answer"] == "正确")
check("判断 判分", t.check_answer("对") and t.check_answer("true") and not t.check_answer("错误"))

# ---- 填空：多空、多答案、可换序 ----
f = FillBlankQuestion(
    "求【1】与【2】的和是【3】。",
    [{"accept": ["4", "四", "肆"]},
     {"accept": ["8"], "group": 1},
     {"accept": ["16"], "group": 1}],
    subject="Java")
ok, d1, _ = rt(f)
check("填空 往返一致", ok)
check("填空 answer 结构", isinstance(d1["answer"], dict) and len(d1["answer"]["items"]) == 3)
check("填空 每空多答案", f.check_answer(["四", "8", "16"]) and f.check_answer(["肆", "16", "8"]))
check("填空 组内换序", f.check_answer(["4", "16", "8"]) and not f.check_answer(["4", "8", "16", "x"]))
check("填空 答案错", not f.check_answer(["4", "8", "9"]))
check("填空 长度错", not f.check_answer(["4", "8"]))
check("填空 answer_text", "第1空: 4/四/肆" in f.answer_text() and "互换" in f.answer_text())

# ---- 简答：不自动判分 ----
e = EssayQuestion("简答", "参考答案", subject="Java")
ok, d1, _ = rt(e)
check("简答 往返一致", ok)
check("简答 非自动判分", not e.is_auto_graded() and e.check_answer("任意") is False)

# ---- 计算：严格 + 数值容差 ----
c = CalculationQuestion("计算", "42", subject="Java")
ok, d1, _ = rt(c)
check("计算 往返一致", ok)
check("计算 数值/文本判分", c.check_answer("42.0") and c.check_answer("42") and not c.check_answer("43") and not c.check_answer("42.1"))
c2 = CalculationQuestion("计算文本", "public", subject="Java")
check("计算 文本严格", c2.check_answer("public") and not c2.check_answer("Public"))

# ---- 图片收集与 images(题后配图) 字段 ----
img_q = SingleChoiceQuestion(
    "看右图\n1.png 然后回答",
    [["A", "选项图 5a.png"], ["B", "纯文本"]], "A", subject="Java")
d = img_q.to_dict()
toks = collect_image_tokens(img_q.text, *([t for _, t in img_q.options]))
check("images字段=题后图(缺省空), 收集含题干与选项token",
      d["images"] == [] and toks == ["1.png", "5a.png"], (d["images"], toks))
check("collect_image_tokens", collect_image_tokens("见 2.png 与 2.png", "x.png") == ["2.png", "x.png"])
img_b = Question.from_dict({"type": "填空题", "text": "看下表：[数据结构/3.png] 求值", "answer": {"items": []}, "subject": "X"})
check("方括号标记收集", collect_image_tokens(img_b.text) == ["数据结构/3.png"])
check("display 屏蔽图片名", "3.png" not in img_b.display() and "（图）" in img_b.display())

# ---- v1 旧格式读取 ----
v1s = {"type": "选择题", "choice_type": "single", "text": "旧单选，图 9.png", "answer": "B",
       "options": [["A", "1"], ["B", "2"]], "multiple_answers": None, "subject": "旧", "flag_star": True}
qs = Question.from_dict(v1s)
check("v1 选择题->单选题", isinstance(qs, SingleChoiceQuestion) and qs.to_dict()["type"] == "单选题" and qs.to_dict()["flag_star"] is True)

v1m = {"type": "选择题", "choice_type": "multiple", "text": "旧多选", "answer": "",
       "options": [["A", "1"], ["B", "2"], ["C", "3"]], "multiple_answers": ["A", "C"], "subject": "旧"}
qm = Question.from_dict(v1m)
check("v1 多选(multiple_answers回填)", isinstance(qm, MultipleChoiceQuestion) and qm.answer == "AC" and qm.to_dict()["answer"] == "AC")

v1f = {"type": "填空题", "text": "在Java中键入(     )命令。", "answer": "java Hello", "subject": "旧"}
qf = Question.from_dict(v1f)
check("v1 填空(括号空+整串答案) -> items", isinstance(qf, FillBlankQuestion)
      and qf.blank_count() == 1 and qf.check_answer("java Hello") and not qf.check_answer("javac"))
check("v1 填空 images", qf.to_dict()["images"] == [])

v1fn = {"type": "填空题", "text": "public class 【1】 { public static 【2】 main(){} }", "answer": "A B", "subject": "旧"}
qfn = Question.from_dict(v1fn)
check("v1 填空【N】多空拆解", qfn.blank_count() == 2 and qfn.check_answer(["A", "B"]) and not qfn.check_answer(["A", "C"]))

# ---- 填空整串模式(whole:true) 往返与判分 ----
wraw = {"type": "填空题", "text": "写出程序输出（整串比对）", "answer": {"whole": True, "items": [{"accept": ["Hello 1"]}]}, "subject": "Java"}
qw = Question.from_dict(wraw)
d = qw.to_dict()
check("whole 整串往返", isinstance(qw, FillBlankQuestion) and qw.whole_string is True
      and d.get("answer") == {"whole": True, "items": [{"accept": ["Hello 1"]}]}, (qw.whole_string, d))
check("whole 判分与空位", qw.blank_count() == 1 and qw.check_answer("Hello 1")
      and not qw.check_answer("Hello 2") and not qw.check_answer(["Hello 1", "x"]))
check("whole answer_text", "Hello 1" in qw.answer_text())

# ---- convert_judge0：题干/选项中的图片文件名在解析后保留 ----
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "convert_tools"))
import convert_judge0 as _cj  # noqa: E402

qs_f = _cj.parse("运行结果如下：\n1.png\n\nHello")
check("judge0 填空题干图片保真", len(qs_f) == 1 and "1.png" in qs_f[0].text
      and "1.png" in collect_image_tokens(qs_f[0].text), [q.text for q in qs_f])
qs_c = _cj.parse("看下图选择\n\n5a.png\n不是\n\nB")
check("judge0 选择题选项图片保真", len(qs_c) == 1 and isinstance(qs_c[0], (ChoiceQuestion, SingleChoiceQuestion))
      and qs_c[0].choice_type == "single"
      and "5a.png" in collect_image_tokens(qs_c[0].text, *([t for _, t in (qs_c[0].options or [])])),
      [q.text for q in qs_c])


print("\n" + ("全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
sys.exit(1 if fails else 0)
