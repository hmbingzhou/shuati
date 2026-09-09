# -*- coding: utf-8 -*-
"""convert_tools 规则自检：PTA 合并/改名 + judge1-6 纯文本 + 加载器元数据。

python convert_tools_selftest.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

fails = []


def check(name, cond, detail=""):
    print(("[ok] " if cond else "[FAIL] ") + name + ("  " + str(detail) if detail and not cond else ""))
    if not cond:
        fails.append(name)


def _load(stem):
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"t_{stem}", os.path.join("convert_tools", stem + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


c1 = _load("convert_judge1")
c2 = _load("convert_judge2")
c3 = _load("convert_judge3")
c4 = _load("convert_judge4")
c5 = _load("convert_judge5")
c6 = _load("convert_judge6")
pt = _load("convert_pta_tf")
pc = _load("convert_pta_choice")
conv0 = _load("convert_judge0")
convert_py = _load("convert")

# ---- 显示名 / 隐藏 / 排序 ----
check("convert 已隐藏", convert_py.JUDGE_HIDDEN is True)
check("名称元数据", c1.JUDGE_NAME == "单选题" and c2.JUDGE_NAME == "多选题" and c3.JUDGE_NAME == "判断题"
      and c4.JUDGE_NAME == "填空题" and c5.JUDGE_NAME == "简答题" and c6.JUDGE_NAME == "计算题"
      and pt.JUDGE_NAME == "PTA判断题" and pc.JUDGE_NAME == "PTA选择题")

from convert_tools.judges import list_judges, get_judge  # noqa: E402
visible = list_judges()
names = [j["name"] for j in visible]
check("列表不含隐藏规则", all(j["id"] != "convert" for j in visible) and "convert" not in names)
check("列表顺序(PTA->judge1..6->直通)", [j["id"] for j in visible] == [
    "convert_pta_tf", "convert_pta_choice", "convert_judge1", "convert_judge2", "convert_judge3",
    "convert_judge4", "convert_judge5", "convert_judge6", "convert_judge0"], [j["id"] for j in visible])
check("get_judge 隐藏规则不可选", get_judge("convert") is None)
hidden_ids = [j["id"] for j in list_judges(include_hidden=True) if j["hidden"]]
check("include_hidden 能列出 convert", hidden_ids == ["convert"], hidden_ids)

# ---- judge1 单选 / judge2 多选（同一排版按字母个数分流） ----
S = "题干一？\n\n选项甲\n选项乙\n\nA\n题干二？\n\n选项甲\n选项乙\n选项丙\n\nAC"
q1 = c1.parse(S)
q2 = c2.parse(S)
check("judge1 单选：单字母1题、多字母跳过", len(q1) == 1 and q1[0].answer == "A")
check("judge2 多选：多字母1题、单字母跳过", len(q2) == 1 and q2[0].answer == "AC" and q2[0].choice_type == "multiple")

# ---- judge3 判断题变体归一 ----
q3 = c3.parse("地球是圆的？\n\n对\n太阳围绕地球转？\n\nF\n1+1=2？\n\n正确")
check("judge3 判断归一", [q.answer for q in q3] == ["正确", "错误", "正确"] and len(q3) == 3, [q.answer for q in q3])

# ---- judge4 填空 [N] -> 【N】 ----
q4 = c4.parse("x[1]加y[2]等于几？\n\n[1]3\n[2]4\n\nx[1]减[2]\n\n[1]1\n[2]2")
check("judge4 填空转规范空位", len(q4) == 2 and q4[0].text == "x【1】加y【2】等于几？"
      and q4[0].check_answer(["3", "4"]) and q4[1].check_answer(["1", "2"]),
      [(q.text, q.answer) for q in q4])

# ---- judge5 简答多行 ----
q5 = c5.parse("简述原理\n\n第一行\n第二行\n\n下一题？\n\n只答一行")
check("judge5 简答", len(q5) == 2 and q5[0].answer == "第一行\n第二行", [(q.text, q.answer) for q in q5])

# ---- judge6 占位 ----
check("judge6 占位返回空", c6.parse("1+1=？\n\n2") == [] and c6.render([]) == "")

# ---- PTA判断题：参考答案 + 末尾 T/F 汇总 ----
T1 = ("分数：2\n作者：a\n单位：b\n命题1地球是圆的？\n\n参考答案\nT\n"
      "分数：2\n作者：a\n单位：b\n命题2太阳绕地球？\n\n参考答案\nF")
t1 = pt.parse(T1)
check("PTA判断：逐题参考答案", [q.answer for q in t1] == ["正确", "错误"], [q.answer for q in t1])
T2 = ("分数：2\n作者：a\n单位：b\n命题1地球是圆的？\n\nT\n"
      "分数：2\n作者：a\n单位：b\n命题2太阳绕地球？\n\nF\nT F")
t2 = pt.parse(T2)
check("PTA判断：末尾 T/F 汇总(并入 judge1 能力)", [q.answer for q in t2] == ["正确", "错误"], [q.answer for q in t2])

# ---- PTA选择题：参考答案优先 + 末尾汇总兜底 ----
C1 = ("分数：3\n作者：a\n单位：b\n题目X？\nA. 甲\nB. 乙\n\n参考答案\nA\n"
      "分数：3\n作者：a\n单位：b\n题目Y？\nA. 丙\nB. 丁\n\n参考答案\nB")
c_ok = pc.parse(C1)
check("PTA选择：逐题参考答案", len(c_ok) == 2 and [q.answer for q in c_ok] == ["A", "B"],
      [(q.text, q.answer) for q in c_ok])

# ---- 图片保真仍有效（judge0 + 题干行内 token 直通）----
img = conv0.parse("运行结果如下：\n1.png\n\nHello")
check("convert_judge0 图片保真", len(img) == 1 and "1.png" in img[0].text
      and "1.png" in img[0].to_dict().get("images", []))

print("\n" + ("convert_tools 自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
sys.exit(1 if fails else 0)
