# -*- coding: utf-8 -*-
"""AI 解析：把排版混乱的原始文本交给 DeepSeek，整理成结构化题目。

- 配置优先读环境变量，其次 data/ai.json（该文件不进版本库）
- 分块调用，块间按题号/空行切分，避免超长
- 输出做严格校验：题型白名单、答案字母必须落在选项内、判断题只有正确/错误
- 任何失败都抛异常，由调用方回退到规则解析
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
CONFIG_NAME = "ai.json"

SYSTEM_PROMPT = """你是题库结构化助手。把用户给的原始文本整理成题目，只输出 JSON，不要任何解释文字。

输出格式：
{"questions":[{"type":"单选题","text":"题干","options":[["A","选项内容"],["B","选项内容"]],"answer":"A"}]}

规则：
1. type 只能是：单选题、多选题、判断题、填空题、简答题、计算题、证明题
2. 选择题必须给 options（至少 2 个），answer 用大写字母；多选题答案按字母顺序连写，如 "ABD"
3. 判断题不给 options，answer 只能是 "正确" 或 "错误"
4. 填空题在 text 里把每个空标成 【1】【2】…；answer 里各空答案用 "||" 分隔，
   同一个空若有多个可接受写法，用 "|" 分隔，如 "奇||偶数|偶"
5. 简答题/计算题/证明题：answer 写参考答案，保留原有换行
6. 原文没有答案时 answer 填空字符串 ""，绝对不要凭空编造答案
7. 题干里的公式、代码、图片占位符原样保留，不要改写
8. 丢弃识别不出的碎片（页眉页脚、页码、目录）
9. 题号、分值、"我的答案"之类的前缀不要写进 text
"""

FILL_PROMPT = """注意：本次允许你根据学科知识补出原题缺失的答案，但必须在该题的 "aiFilled" 字段写 true，
原有答案的题写 false 或省略。补出的答案要尽量准确，宁可写 "" 也不要瞎猜。
"""

TYPE_WHITELIST = {"单选题", "多选题", "判断题", "填空题", "简答题", "计算题", "证明题"}
CHOICE_TYPES = {"单选题", "多选题"}


class AIError(RuntimeError):
    """AI 调用或结果校验失败"""


# ---------------------------------------------------------------- 配置

def _config_path():
    from utils import paths
    return os.path.join(paths.DATA_DIR, CONFIG_NAME)


def load_config():
    """返回 {apiKey, baseUrl, model, source}；source 表明配置来自哪里"""
    cfg = {"apiKey": "", "baseUrl": DEFAULT_BASE_URL, "model": DEFAULT_MODEL, "source": ""}
    path = _config_path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            for k in ("apiKey", "api_key", "key"):
                if raw.get(k):
                    cfg["apiKey"] = str(raw[k]).strip()
                    cfg["source"] = "data/ai.json"
                    break
            if raw.get("baseUrl"):
                cfg["baseUrl"] = str(raw["baseUrl"]).rstrip("/")
            if raw.get("model"):
                cfg["model"] = str(raw["model"])
        except (OSError, ValueError):
            pass
    if os.environ.get("AI_API_KEY"):
        cfg["apiKey"] = os.environ["AI_API_KEY"].strip()
        cfg["source"] = "环境变量"
    if os.environ.get("AI_BASE_URL"):
        cfg["baseUrl"] = os.environ["AI_BASE_URL"].rstrip("/")
    if os.environ.get("AI_MODEL"):
        cfg["model"] = os.environ["AI_MODEL"]
    return cfg


def save_config(api_key: str, base_url: str = "", model: str = ""):
    """把 key 写进 data/ai.json（不进版本库）"""
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"apiKey": (api_key or "").strip()}
    if base_url:
        data["baseUrl"] = base_url.rstrip("/")
    if model:
        data["model"] = model
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return True


def clear_config():
    """删除本地保存的密钥（data/ai.json）"""
    path = _config_path()
    if os.path.isfile(path):
        os.remove(path)
    return True


def masked_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 12:
        return key[:3] + "***"
    return f"{key[:6]}...{key[-4:]}"


# ---------------------------------------------------------------- HTTP

def _post(cfg, messages, timeout=120, max_tokens=8000):
    if not cfg.get("apiKey"):
        raise AIError("没有配置 AI 密钥（data/ai.json 或环境变量 AI_API_KEY）")
    url = cfg["baseUrl"].rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['apiKey']}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        if e.code == 401:
            raise AIError("AI 密钥无效（401）") from e
        if e.code == 402:
            raise AIError("AI 账户余额不足（402）") from e
        if e.code == 429:
            raise AIError("AI 请求过于频繁（429），稍后再试") from e
        raise AIError(f"AI 接口返回 {e.code}：{detail}") from e
    except urllib.error.URLError as e:
        raise AIError(f"连不上 AI 接口：{getattr(e, 'reason', e)}") from e
    except TimeoutError as e:
        raise AIError("AI 请求超时") from e


def test_key(timeout=40):
    """自检：发一句最小请求，返回 {ok, reply, model, elapsed, usage}"""
    cfg = load_config()
    t0 = time.time()
    data = _post(cfg, [{"role": "user", "content": "只回复两个字：在线"}],
                 timeout=timeout, max_tokens=10)
    elapsed = round(time.time() - t0, 2)
    try:
        reply = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise AIError(f"AI 返回格式异常：{str(data)[:200]}") from e
    return {"ok": True, "reply": reply, "model": cfg["model"],
            "baseUrl": cfg["baseUrl"], "elapsed": elapsed,
            "usage": data.get("usage"), "key": masked_key(cfg["apiKey"]),
            "source": cfg["source"]}


# ---------------------------------------------------------------- 文本分块

def split_chunks(text: str, limit: int = 2500):
    """按题号/空行把长文本切成若干块，块不超过 limit 字符"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) <= limit:
        return [text] if text else []
    lines = text.split("\n")
    chunks, cur, size = [], [], 0
    for line in lines:
        if size + len(line) + 1 > limit and cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


# ---------------------------------------------------------------- 解析与校验

def _extract_json(raw: str):
    """从模型输出里抠出 JSON 对象（容忍 ```json 包裹和前后废话）"""
    if not raw:
        raise AIError("AI 返回为空")
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    if not s.startswith("{"):
        i = s.find("{")
        j = s.rfind("}")
        if i == -1 or j <= i:
            raise AIError(f"AI 返回的不是 JSON：{raw[:150]}")
        s = s[i:j + 1]
    try:
        return json.loads(s)
    except ValueError:
        # 常见：最后一个逗号、单引号
        s2 = re.sub(r",\s*([}\]])", r"\1", s)
        try:
            return json.loads(s2)
        except ValueError as e:
            raise AIError(f"AI 返回的 JSON 解析失败：{raw[:150]}") from e


def _normalize_type(t: str, options, answer: str) -> str:
    t = (t or "").strip()
    if t in TYPE_WHITELIST:
        if t in CHOICE_TYPES and not options:
            return "判断题" if str(answer).strip() in ("正确", "错误") else "简答题"
        if t == "判断题" and options:
            return "单选题"
        return t
    # 模型偶尔写英文/别名
    alias = {"single": "单选题", "multiple": "多选题", "multi": "多选题", "judge": "判断题",
             "truefalse": "判断题", "blank": "填空题", "fill": "填空题", "essay": "简答题",
             "short": "简答题", "calc": "计算题", "计算": "计算题", "proof": "证明题"}
    if t.lower() in alias:
        return alias[t.lower()]
    if options and len(options) >= 2:
        return "多选题" if len(re.sub(r"[^A-Za-z]", "", str(answer))) > 1 else "单选题"
    if str(answer).strip() in ("正确", "错误", "对", "错", "√", "×", "T", "F"):
        return "判断题"
    if re.search(r"【\d+】|_{2,}", str(answer) or ""):
        return "填空题"
    return "简答题"


def _normalize_options(raw):
    opts = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            k = str(k).strip().upper()[:1]
            if k and k.isalpha():
                opts.append([k, str(v).strip()])
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                opts.append([str(item[0]).strip().upper()[:1], str(item[1]).strip()])
            elif isinstance(item, str):
                m = re.match(r"^\s*([A-Ha-h])\s*[.、．)）:：]\s*(.+)$", item)
                if m:
                    opts.append([m.group(1).upper(), m.group(2).strip()])
                elif opts:
                    opts[-1][1] += " " + item.strip()
    opts.sort(key=lambda x: x[0])
    return opts


def _normalize_answer(tp: str, answer, options):
    """把模型给的 answer 规范成程序认识的形状；不合规返回 None"""
    if tp == "判断题":
        v = str(answer or "").strip()
        low = v.lower()
        if v in ("正确", "对", "√", "是", "T", "t", "true", "yes") or low in ("t", "true", "yes"):
            return "正确"
        if v in ("错误", "错", "×", "否", "F", "f", "false", "no") or low in ("f", "false", "no"):
            return "错误"
        return None

    if tp in CHOICE_TYPES:
        letters = [o[0] for o in options]
        ans = re.sub(r"[^A-Za-z]", "", str(answer or "")).upper()
        ans = "".join(sorted(set(ans)))
        if not ans or any(c not in letters for c in ans):
            return None
        return ans

    if tp == "填空题":
        s = str(answer or "").strip()
        if not s:
            return None
        blanks = [b.strip() for b in re.split(r"\|\|", s)]
        items = []
        for b in blanks:
            accepts = [a.strip() for a in re.split(r"[|｜]", b) if a.strip()]
            if not accepts:
                accepts = [""]
            items.append({"accept": accepts})
        return {"items": items}

    s = str(answer or "").strip()
    return s or None


def normalize_draft(d):
    """校验并规范化单条题目；不合规返回 None"""
    if not isinstance(d, dict):
        return None
    text = str(d.get("text") or "").strip()
    if len(text) < 2:
        return None
    options = _normalize_options(d.get("options"))
    tp = _normalize_type(d.get("type"), options, d.get("answer"))
    answer = _normalize_answer(tp, d.get("answer"), options)
    if answer is None:
        return None
    out = {"type": tp, "text": text, "answer": answer}
    if tp in CHOICE_TYPES:
        if len(options) < 2:
            return None
        out["options"] = options
    if d.get("aiFilled"):
        out["aiFilled"] = True
    return out


def parse_text_ai(text: str, subject: str = "", fill_missing: bool = False,
                  chunk_limit: int = 2500, timeout: int = 120, progress=None):
    """调用 AI 解析文本；返回 {drafts, warnings, usage, chunks}"""
    cfg = load_config()
    if not cfg.get("apiKey"):
        raise AIError("没有配置 AI 密钥（data/ai.json 或环境变量 AI_API_KEY）")
    text = (text or "").strip()
    if not text:
        raise AIError("请粘贴要解析的文本")

    chunks = split_chunks(text, chunk_limit)
    system = SYSTEM_PROMPT + (FILL_PROMPT if fill_missing else "")
    drafts, warnings, usage = [], [], {"prompt_tokens": 0, "completion_tokens": 0}
    for idx, chunk in enumerate(chunks, 1):
        if progress:
            progress(idx, len(chunks))
        user = f"学科：{subject or '未指定'}\n\n原始文本：\n{chunk}"
        data = _post(cfg, [{"role": "system", "content": system},
                           {"role": "user", "content": user}], timeout=timeout)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            warnings.append(f"第 {idx} 块返回格式异常，已跳过")
            continue
        u = data.get("usage") or {}
        usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
        usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
        try:
            obj = _extract_json(content)
        except AIError as e:
            warnings.append(f"第 {idx} 块：{e}")
            continue
        items = obj.get("questions") if isinstance(obj, dict) else obj
        if not isinstance(items, list):
            warnings.append(f"第 {idx} 块返回的 questions 不是数组，已跳过")
            continue
        before = len(drafts)
        for raw in items:
            d = normalize_draft(raw)
            if d:
                drafts.append(d)
        if len(drafts) == before:
            warnings.append(f"第 {idx} 块没有可用的题目（可能是纯文本碎片）")
    return {"drafts": drafts, "warnings": warnings, "usage": usage, "chunks": len(chunks),
            "model": cfg["model"]}
