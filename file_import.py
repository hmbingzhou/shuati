# -*- coding: utf-8 -*-
"""文件导入：把 Word / Excel / CSV / Markdown / TXT 解析成题目草稿。

纯标准库实现（zipfile + xml.etree），不引第三方依赖。

对外主入口：
    parse_file(filename, raw_bytes, subject="") -> {
        "drafts": [{type, text, options, answer, source}],
        "warnings": [str],
        "images": [{"name": str, "bytes": bytes, "ref": ref}],
        "stats": {"total": n, "byType": {...}},
    }
图片不会自动落盘，由调用方（webui_server）保存到 pictures/<subject>/ 并用 token 替换 ref。
"""
import csv
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET

SUPPORTED_EXT = (".docx", ".xlsx", ".csv", ".tsv", ".md", ".markdown", ".txt")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


# ---------------------------------------------------------------- 文本工具

def decode_bytes(raw: bytes) -> str:
    """尽量正确地解码文本（UTF-8 / GB18030 / UTF-16）"""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    for enc in ("gb18030", "utf-16", "big5"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


ANS_LINE = re.compile(r"^\s*(?:我的答案|正确答案|参考答案|标准答案|答案)\s*[:：]\s*(.*)$")
ITEM_HEAD = re.compile(r"^\s*(?:\d{1,3}|[（(]\s*\d{1,3}\s*[)）])\s*[、.．)）]?\s*")
OPT_MARK = re.compile(r"(?<![A-Za-z0-9])([A-H])\s*[、.．)）]\s*")
TF_WORDS = {"正确", "错误", "对", "错", "√", "×", "t", "f", "true", "false", "yes", "no", "是", "否"}


def _norm_ans(raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"^[（(]\s*", "", s)
    s = re.sub(r"\s*[)）]$", "", s)
    return s.strip("。.;；,，")


def split_options(text: str):
    """从一段文字里切出 (题干, 选项列表)；切不出返回 ("", [])"""
    for pat in (r"(?<![A-Za-z0-9])([A-H])\s*[、.．)）]\s*", r"([A-H])\s*[、.．)）]\s*"):
        marks = list(re.finditer(pat, text))
        if len(marks) < 2:
            continue
        letters = [m.group(1).upper() for m in marks]
        if letters != sorted(letters) or len(set(letters)) != len(letters):
            continue
        stem = text[:marks[0].start()].strip()
        opts = []
        for k, m in enumerate(marks):
            end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
            val = text[m.end():end].strip(" \t,，;；。")
            opts.append([m.group(1).upper(), val])
        return stem, opts
    return "", []


def _classify(stem: str, opts, answer: str, body: str, hint: str = None):
    """根据有没有选项 / 答案长什么样，判断题型并产出草稿"""
    stem = re.sub(r"\s+", " ", stem or "").strip()
    answer = (answer or "").strip()
    if not stem:
        return None
    if opts and len(opts) >= 2:
        letters = [o[0] for o in opts]
        ans = re.sub(r"[^A-Za-z]", "", answer).upper()
        if ans and all(c in letters for c in ans) and len(ans) >= 1:
            tp = hint if hint in ("单选题", "多选题") else ("多选题" if len(ans) > 1 else "单选题")
            return {"type": tp, "text": stem, "options": opts, "answer": ans}
        return None
    if answer and answer.strip().lower() in TF_WORDS:
        v = answer.strip()
        v = "正确" if v in ("正确", "对", "√", "t", "T", "true", "是", "yes") else "错误"
        return {"type": "判断题", "text": stem, "answer": v}
    if hint == "简答题":
        return {"type": "简答题", "text": stem, "answer": answer} if answer else None
    if answer:
        # 题干里有空位 → 填空；否则简答（答案较长时）
        has_blank = bool(re.search(r"[（(]\s*[)）]|_{2,}|【\d+】", stem))
        if (hint == "填空题" or has_blank) and len(answer) <= 60:
            return {"type": "填空题", "text": re.sub(r"[（(]\s*[)）]", "【1】", stem),
                    "answer": {"items": [{"accept": [answer]}]}}
        return {"type": "简答题", "text": stem, "answer": answer}
    return None


ANS_MARK = re.compile(r"(?:我的答案|正确答案|参考答案|标准答案|答案)\s*[:：]\s*")


def _split_by_answer(text: str):
    """按「答案X」切段，返回 [(题干文本, 答案文本)]。

    支持一行里出现多个答案标记（如「我的答案:D 正确答案: C」），
    后一个答案会覆盖前一个。
    """
    marks = list(ANS_MARK.finditer(text))
    if not marks:
        return [(text, "")]
    segs = []
    prev_end = 0
    for m in marks:
        stem = text[prev_end:m.start()]
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        ans = text[m.end():line_end].strip()
        segs.append([stem, ans])
        prev_end = line_end
    tail = text[prev_end:]
    if tail.strip():
        segs.append([tail, ""])
    # 空段（只有空白）说明是同一个题目的第二个答案，覆盖上一个
    merged = []
    for stem, ans in segs:
        if not stem.strip() and merged and ans:
            merged[-1][1] = ans
            continue
        merged.append([stem, ans])
    return [(s, a) for s, a in merged]


TYPE_TAG = re.compile(r"[（(]\s*(单选题|多选题|判断题|填空题|简答题|计算题|证明题)\s*(?:[,，]\s*[\d.]+\s*分)?\s*[)）]")


def parse_text(text: str):
    """规则解析：支持「题号 + 题干 + 选项 + 答案」常见排版"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    drafts = []
    for stem_raw, ans in _split_by_answer(text):
        stem_raw = stem_raw.strip()
        if not stem_raw:
            continue
        lines = [l for l in stem_raw.split("\n") if l.strip()]
        # 段首若是「标题行」（短、无标点、下一行才是题号），丢掉它
        if len(lines) >= 2 and len(lines[0].strip()) <= 20 \
                and not re.search(r"[。？！.?!]$", lines[0].strip()) \
                and ITEM_HEAD.match(lines[1].strip()):
            lines = lines[1:]
        stem_raw = "\n".join(lines)
        # 去掉「(单选题,1.0分)」这类题型标记，顺便当作类型提示
        hint = None
        m = TYPE_TAG.search(stem_raw)
        if m:
            hint = m.group(1)
            stem_raw = (stem_raw[:m.start()] + stem_raw[m.end():]).strip()
        # 去掉题号前缀
        stem_raw = ITEM_HEAD.sub("", stem_raw, count=1).strip()
        joined = re.sub(r"[ \t]{2,}", " ", stem_raw)
        stem, opts = split_options(joined)
        if not opts:
            stem = joined
        draft = _classify(stem, opts, ans, joined, hint)
        if draft:
            draft["source"] = joined[:80]
            drafts.append(draft)
    return drafts


# ---------------------------------------------------------------- docx

def _docx_rels(z: zipfile.ZipFile):
    """rId -> media 文件名"""
    try:
        data = z.read("word/_rels/document.xml.rels")
    except KeyError:
        return {}
    root = ET.fromstring(data)
    out = {}
    for rel in root.iter(PKG_REL + "Relationship"):
        target = rel.get("Target") or ""
        if "media/" in target:
            out[rel.get("Id")] = os.path.basename(target)
    return out


def _para_text(p, rels, media_used, images):
    """按顺序取出段落里的文字与图片，图片用占位符 [[IMG:name]] 表示"""
    parts = []
    for node in p.iter():
        tag = node.tag
        if tag == W + "t":
            parts.append(node.text or "")
        elif tag == W + "tab":
            parts.append("\t")
        elif tag == W + "br":
            parts.append("\n")
        elif tag == A + "blip":
            rid = node.get(R + "embed")
            name = rels.get(rid)
            if name:
                media_used.add(name)
                parts.append(f"[[IMG:{name}]]")
    return "".join(parts)


def _docx_doc_and_tables(raw: bytes):
    """返回 (按文档顺序的段落文本列表, 表格列表)；表格每行是单元格文本列表"""
    z = zipfile.ZipFile(io.BytesIO(raw))
    rels = _docx_rels(z)
    media_used = set()
    images = []
    for name in z.namelist():
        if name.startswith("word/media/"):
            images.append({"name": os.path.basename(name), "bytes": z.read(name)})

    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    paras, tables = [], []
    if body is None:
        return paras, tables
    for child in body:
        if child.tag == W + "p":
            txt = _para_text(child, rels, media_used, images)
            if txt.strip():
                paras.append(txt)
        elif child.tag == W + "tbl":
            rows = []
            for tr in child.findall(W + "tr"):
                cells = []
                for tc in tr.findall(W + "tc"):
                    cell_txt = " ".join(_para_text(p, rels, media_used, images)
                                        for p in tc.findall(W + "p")).strip()
                    cells.append(cell_txt)
                if any(c for c in cells):
                    rows.append(cells)
            if rows:
                tables.append(rows)
    return paras, tables


def _table_drafts(rows):
    """把「表头 + 数据行」的表格映射成题目；表头不认识就返回 []"""
    if len(rows) < 2:
        return []
    head = [re.sub(r"\s+", "", c) for c in rows[0]]

    def col(*names):
        for n in names:
            for i, h in enumerate(head):
                if n in h:
                    return i
        return None

    i_type = col("题型", "类型")
    i_text = col("题干", "题目", "问题")
    i_opts = col("选项", "备选")
    i_ans = col("答案", "正确答案", "参考答案")
    if i_text is None or i_ans is None:
        return []

    out = []
    for row in rows[1:]:
        # 行比表头长（单元格里带了分隔符，如选项用 | 分隔）：把多出来的并进选项列
        extra = len(row) - len(head)
        if extra > 0 and i_opts is not None and i_ans is not None and i_ans > i_opts:
            tail = len(row) - (len(head) - i_ans)
            row = row[:i_opts] + ["|".join(row[i_opts:tail])] + row[tail:]

        def get(i, _row=row):
            return _row[i].strip() if i is not None and i < len(_row) else ""

        text = get(i_text)
        answer = get(i_ans)
        if not text or not answer:
            continue
        opts_raw = get(i_opts)
        opts = []
        if opts_raw:
            _, opts = split_options(opts_raw if opts_raw.upper().startswith("A") else "A" + opts_raw)
        tp = get(i_type)
        draft = None
        if opts:
            ans = re.sub(r"[^A-Za-z]", "", answer).upper()
            draft = {"type": tp or ("多选题" if len(ans) > 1 else "单选题"),
                     "text": text, "options": opts, "answer": ans}
        elif tp in ("判断题", "填空题", "简答题", "计算题", "证明题"):
            if tp == "判断题":
                v = answer.strip().lower()
                draft = {"type": "判断题", "text": text,
                         "answer": "正确" if v in ("正确", "对", "√", "t", "true", "yes", "是") else "错误"}
            elif tp == "填空题":
                draft = {"type": "填空题", "text": text,
                         "answer": {"items": [{"accept": [x.strip()]} for x in re.split(r"[；;|]", answer) if x.strip()]}}
            else:
                draft = {"type": tp, "text": text, "answer": answer}
        else:
            draft = _classify(text, [], answer, text)
        if draft:
            draft["source"] = "表格"
            out.append(draft)
    return out


def parse_docx(raw: bytes):
    paras, tables = _docx_doc_and_tables(raw)
    drafts = []
    # 表格优先（结构最可靠），段落里可能还有单独的题目，两边都解析后去重
    for rows in tables:
        drafts.extend(_table_drafts(rows))
    para_text = "\n".join(paras)
    if para_text.strip():
        drafts.extend(parse_text(para_text))
    # 去重（同题干同答案只留一条）
    seen, uniq = set(), []
    for d in drafts:
        key = (re.sub(r"\s+", "", d["text"])[:60], str(d.get("answer"))[:40])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    images = []
    z = zipfile.ZipFile(io.BytesIO(raw))
    for name in z.namelist():
        if name.startswith("word/media/"):
            images.append({"name": os.path.basename(name), "bytes": z.read(name)})
    warnings = []
    if images:
        warnings.append(f"文档内含 {len(images)} 张图片，已提取；题目里的图片位置会自动替换成图片引用")
    return uniq, images, warnings


# ---------------------------------------------------------------- xlsx

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def parse_xlsx(raw: bytes):
    z = zipfile.ZipFile(io.BytesIO(raw))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(S + "si"):
            shared.append("".join(t.text or "" for t in si.iter(S + "t")))
    sheets = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    sheets.sort()
    if not sheets:
        return [], [], ["Excel 里没找到工作表"]
    root = ET.fromstring(z.read(sheets[0]))
    rows = []
    for row in root.iter(S + "row"):
        vals = []
        for c in row.findall(S + "c"):
            t = c.get("t")
            v = c.find(S + "v")
            if t == "s" and v is not None:
                idx = int(v.text or "0")
                vals.append(shared[idx] if 0 <= idx < len(shared) else "")
            elif t == "inlineStr":
                is_el = c.find(S + "is")
                vals.append("".join(x.text or "" for x in is_el.iter(S + "t")) if is_el is not None else "")
            else:
                vals.append((v.text or "") if v is not None else "")
        if any(x.strip() for x in vals):
            rows.append(vals)
    if not rows:
        return [], [], ["工作表是空的"]
    drafts = _table_drafts(rows)
    if drafts:
        return drafts, [], []
    # 没有表头：整表当文本
    text = "\n".join("  ".join(c for c in r if c) for r in rows)
    return parse_text(text), [], []


# ---------------------------------------------------------------- 文本类

def parse_delimited(raw: bytes, delimiter=','):
    text = decode_bytes(raw)
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        return [], ["文件是空的"]
    drafts = _table_drafts(rows)
    if drafts:
        return drafts, []
    flat = "\n".join("  ".join(c for c in r if c) for r in rows)
    return parse_text(flat), []


def parse_markdown(raw: bytes):
    text = decode_bytes(raw)
    # 管道表格 → 行
    rows = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                rows.append(cells)
        elif rows and not s:
            pass
    drafts = _table_drafts(rows) if rows else []
    if drafts:
        return drafts, []
    # 去 markdown 标记后按纯文本解析
    plain = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", plain)
    plain = re.sub(r"^\s{0,3}#{1,6}\s*", "", plain, flags=re.M)
    plain = re.sub(r"[*_`]{1,3}", "", plain)
    return parse_text(plain), []


# ---------------------------------------------------------------- 主入口

def parse_file(filename: str, raw: bytes, subject: str = ""):
    ext = os.path.splitext(filename or "")[1].lower()
    warnings, images = [], []
    if ext == ".docx":
        drafts, images, warnings = parse_docx(raw)
    elif ext == ".xlsx":
        drafts, images, warnings = parse_xlsx(raw)
    elif ext in (".csv",):
        drafts, warnings = parse_delimited(raw, ",")
    elif ext in (".tsv",):
        drafts, warnings = parse_delimited(raw, "\t")
    elif ext in (".md", ".markdown"):
        drafts, warnings = parse_markdown(raw)
    elif ext in (".txt",):
        drafts, warnings = parse_text(decode_bytes(raw)), []
    else:
        raise ValueError(f"不支持的文件类型：{ext or '（无扩展名）'}；支持 {', '.join(SUPPORTED_EXT)}")

    # 图片占位符 [[IMG:x]] → 图片 token（由调用方决定最终路径）
    if images:
        img_names = {img["name"] for img in images}
        for d in drafts:
            for field in ("text",):
                d[field] = re.sub(r"\[\[IMG:([^\]]+)\]\]",
                                  lambda m: f"[{subject}/{m.group(1)}]" if subject else f"[{m.group(1)}]",
                                  d[field])
    by_type = {}
    for d in drafts:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
    return {"drafts": drafts, "images": images, "warnings": warnings,
            "stats": {"total": len(drafts), "byType": by_type}}
