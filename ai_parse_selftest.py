# -*- coding: utf-8 -*-
"""自检：AI 解析的纯逻辑部分（不联网）。

覆盖：配置读写与掩码、文本分块、模型输出容错、题型/答案规范化。
真实调用 API 不在自检范围内（需要联网和密钥），由界面上的「解析」按钮实测。
运行：python ai_parse_selftest.py
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".probe_ai_selftest")
shutil.rmtree(HOME, ignore_errors=True)
os.makedirs(os.path.join(HOME, "data"), exist_ok=True)
os.environ["SHUATI_HOME"] = HOME
os.environ.pop("AI_API_KEY", None)

import ai_parse  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


# ---------- 1) 配置 ----------
check("未配置时 configured 为空", ai_parse.load_config()["apiKey"] == "")
ai_parse.save_config("sk-abcdef1234567890", "https://api.deepseek.com", "deepseek-chat")
cfg = ai_parse.load_config()
check("保存后能读回 key", cfg["apiKey"] == "sk-abcdef1234567890", cfg)
check("baseUrl/model 一并保存", cfg["baseUrl"] == "https://api.deepseek.com" and cfg["model"] == "deepseek-chat", cfg)
check("掩码不泄露完整 key", ai_parse.masked_key(cfg["apiKey"]) == "sk-abc...7890", ai_parse.masked_key(cfg["apiKey"]))
check("配置文件落在 data/ai.json", os.path.isfile(os.path.join(HOME, "data", "ai.json")))

os.environ["AI_API_KEY"] = "sk-env-override"
check("环境变量优先级高于文件", ai_parse.load_config()["apiKey"] == "sk-env-override", ai_parse.load_config()["source"])
os.environ.pop("AI_API_KEY", None)

ai_parse.clear_config()
check("清除后配置文件被删除", not os.path.isfile(os.path.join(HOME, "data", "ai.json")))
check("清除后读不到 key", ai_parse.load_config()["apiKey"] == "")
ai_parse.save_config("sk-abcdef1234567890")

# ---------- 2) 分块 ----------
short = "1. 题目\n答案：A"
check("短文本不分块", ai_parse.split_chunks(short) == [short])
long_text = "\n".join(f"{i}. 这是第{i}道题的题干，内容随便写一点凑长度。\n答案：A" for i in range(1, 201))
chunks = ai_parse.split_chunks(long_text, limit=800)
check("长文本被切成多块", len(chunks) > 1, len(chunks))
check("每块不超过上限", all(len(c) <= 900 for c in chunks), [len(c) for c in chunks])
check("拼回去不丢内容", "".join(chunks).count("答案：A") == 200, "".join(chunks).count("答案：A"))

# ---------- 3) 模型输出容错 ----------
obj = ai_parse._extract_json('{"questions":[{"type":"单选题"}]}')
check("解析裸 JSON", obj["questions"][0]["type"] == "单选题", obj)
obj = ai_parse._extract_json('好的，结果如下：\n```json\n{"questions":[]}\n```\n以上。')
check("剥掉 ```json 包裹和前后废话", obj == {"questions": []}, obj)
obj = ai_parse._extract_json('{"questions":[{"a":1},]}')
check("容忍多余逗号", obj["questions"][0]["a"] == 1, obj)
try:
    ai_parse._extract_json("我解析不出来")
    check("非 JSON 应报错", False)
except ai_parse.AIError:
    check("非 JSON 应报错", True)

# ---------- 4) 题型与答案规范化 ----------
d = ai_parse.normalize_draft({"type": "单选题", "text": "题干",
                              "options": {"A": "甲", "B": "乙"}, "answer": "b"})
check("选项字典→数组、答案大写", d["options"] == [["A", "甲"], ["B", "乙"]] and d["answer"] == "B", d)

d = ai_parse.normalize_draft({"type": "多选题", "text": "题干",
                              "options": [["A", "1"], ["B", "2"], ["C", "3"]], "answer": "c,a"})
check("多选答案排序去重", d["answer"] == "AC", d)

d = ai_parse.normalize_draft({"type": "判断题", "text": "题干", "answer": "T"})
check("判断题 T→正确", d["answer"] == "正确", d)
d = ai_parse.normalize_draft({"type": "判断题", "text": "题干", "answer": "错"})
check("判断题 错→错误", d["answer"] == "错误", d)

d = ai_parse.normalize_draft({"type": "填空题", "text": "【1】和【2】", "answer": "甲||乙|B"})
check("填空 || 分空、| 分同义答案",
      d["answer"] == {"items": [{"accept": ["甲"]}, {"accept": ["乙", "B"]}]}, d)

check("答案字母不在选项里 → 丢弃",
      ai_parse.normalize_draft({"type": "单选题", "text": "题干",
                                "options": [["A", "1"], ["B", "2"]], "answer": "D"}) is None)
check("题干太短 → 丢弃", ai_parse.normalize_draft({"type": "判断题", "text": "", "answer": "正确"}) is None)
check("选择题没选项 → 降级", 
      (ai_parse.normalize_draft({"type": "单选题", "text": "题干", "answer": "正确"}) or {}).get("type") == "判断题")

d = ai_parse.normalize_draft({"type": "essay", "text": "简述 TCP 握手", "answer": "三次握手"})
check("英文题型别名→简答题", d["type"] == "简答题", d)

d = ai_parse.normalize_draft({"type": "单选题", "text": "题干",
                              "options": [["A", "1"], ["B", "2"]], "answer": "A", "aiFilled": True})
check("AI 补答标记被保留", d.get("aiFilled") is True, d)

# ---------- 5) 没有 key 时应当明确报错 ----------
shutil.rmtree(HOME, ignore_errors=True)
os.environ["SHUATI_HOME"] = HOME
try:
    ai_parse.parse_text_ai("1. 题目\n答案：A")
    check("无 key 时抛错", False)
except ai_parse.AIError as e:
    check("无 key 时抛错", "密钥" in str(e), str(e))

shutil.rmtree(HOME, ignore_errors=True)
print("\n" + ("AI 解析逻辑自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
sys.exit(1 if fails else 0)
