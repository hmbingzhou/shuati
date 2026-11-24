# -*- coding: utf-8 -*-
"""导出：把题库 / 试卷 / 错题本变成能打印、能分享的文件（纯标准库）。

支持两种格式：
- html  打印版，图片以 base64 内嵌，单文件自包含；浏览器 Ctrl+P 可直接另存 PDF
- md    Markdown，方便贴到笔记软件或发给别人

用法：
    data, filename, ctype = export_bank("计算机网络技术", questions, "html", with_answers=True)
"""
import base64
import html as _html
import os
import time

from models.question import collect_image_tokens

PICTURES_DIR = None  # 由调用方注入（webui_server 里设置）

_IMG_CACHE = {}
_MAX_IMG_BYTES = 6 * 1024 * 1024


def set_pictures_dir(path):
    global PICTURES_DIR
    PICTURES_DIR = path


# ---------------------------------------------------------------- 图片

def _find_image(token: str, subject: str):
    """把 [科目/xx.png] 解析成实际文件路径"""
    if not token or not PICTURES_DIR:
        return None
    token = token.strip().lstrip("/")
    candidates = [os.path.join(PICTURES_DIR, token)]
    base = os.path.basename(token)
    if subject:
        candidates.append(os.path.join(PICTURES_DIR, subject, base))
    candidates.append(os.path.join(PICTURES_DIR, base, ))
    for p in candidates:
        if os.path.isfile(p) and os.path.getsize(p) <= _MAX_IMG_BYTES:
            return p
    return None


def _data_uri(path: str):
    if path in _IMG_CACHE:
        return _IMG_CACHE[path]
    ext = os.path.splitext(path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
            ".svg": "image/svg+xml"}.get(ext, "image/png")
    try:
        with open(path, "rb") as f:
            data = f.read()
        uri = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    except OSError:
        uri = None
    _IMG_CACHE[path] = uri
    return uri


def clear_image_cache():
    _IMG_CACHE.clear()


# ---------------------------------------------------------------- 富文本

def _esc(s):
    return _html.escape(str(s or ""))


def rich_html(text: str, subject: str = "") -> str:
    """把题干里的图片 token 换成内嵌图片，其余按纯文本转义并保留换行"""
    s = str(text or "")
    if not s:
        return ""
    tokens = [t for t in collect_image_tokens(s)]
    parts = []
    i = 0
    # 按 token 出现顺序切分
    spans = []
    for tok in tokens:
        for m in _find_token_spans(s, tok, i):
            spans.append(m)
    spans.sort()
    if not spans:
        return _esc(s).replace("\n", "<br>")
    for start, end, tok in spans:
        if start < i:
            continue
        parts.append(_esc(s[i:start]).replace("\n", "<br>"))
        path = _find_image(tok, subject)
        uri = _data_uri(path) if path else None
        if uri:
            parts.append(f'<img class="qimg" src="{uri}" alt="{_esc(tok)}">')
        else:
            parts.append(f'<span class="img-missing">［图片缺失：{_esc(tok)}］</span>')
        i = end
    parts.append(_esc(s[i:]).replace("\n", "<br>"))
    return "".join(parts)


def _find_token_spans(s, tok, after=0):
    """token 可能写成 [学科/a.png] 或裸 a.png，两种都找"""
    out = []
    for form in (f"[{tok}]", tok):
        idx = after
        while True:
            j = s.find(form, idx)
            if j == -1:
                break
            if form == tok:
                # 裸 token 要求两侧不是字母数字，避免误伤 1.png 中的 0.png
                left_ok = j == 0 or not (s[j - 1].isalnum() or s[j - 1] in "./")
                right_ok = j + len(form) >= len(s) or not (s[j + 1].isalnum() or s[j + 1] in "./")
                if not (left_ok and right_ok):
                    idx = j + len(form)
                    continue
            out.append((j, j + len(form), tok))
            idx = j + len(form)
    return out


def rich_markdown(text: str, subject: str = "") -> str:
    return str(text or "")


# ---------------------------------------------------------------- 题目块

def _options_html(q) -> str:
    opts = getattr(q, "options", None) or []
    if not opts:
        return ""
    cells = "".join(
        f'<div class="opt"><b>{_esc(k)}.</b> {rich_html(v, q.subject)}</div>'
        for k, v in opts
    )
    return f'<div class="opts">{cells}</div>'


def _options_md(q) -> str:
    opts = getattr(q, "options", None) or []
    if not opts:
        return ""
    return "\n".join(f"- **{k}.** {v}" for k, v in opts)


def _answer_text(q) -> str:
    try:
        return q.answer_text() or ""
    except Exception:  # noqa: BLE001
        return str(getattr(q, "answer", "") or "")


def question_html(q, no: int, with_answers: bool) -> str:
    tp = q.get_type_name()
    body = [f'<div class="q"><div class="qt"><span class="qno">{no}.</span>'
            f'<span class="qtype">{_esc(tp)}</span>{rich_html(q.text, q.subject)}</div>']
    opts = _options_html(q)
    if opts:
        body.append(opts)
    elif tp in ("简答题", "计算题", "证明题"):
        body.append('<div class="answer-lines"></div>' if not with_answers else "")
    elif tp == "填空题" and not with_answers:
        body.append('<div class="answer-lines sm"></div>')
    if with_answers:
        ans = _answer_text(q)
        body.append(f'<div class="ans">{rich_html(ans, q.subject)}</div>')
    body.append("</div>")
    return "".join(body)


def question_md(q, no: int, with_answers: bool) -> str:
    tp = q.get_type_name()
    lines = [f"**{no}. [{tp}]** {q.text}", ""]
    o = _options_md(q)
    if o:
        lines += [o, ""]
    if with_answers:
        lines += [f"**答案：** {_answer_text(q)}", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 文档模板

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "PingFang SC", "Songti SC", serif;
       color: #1b1b1f; line-height: 1.75; margin: 0 auto; max-width: 860px; padding: 24px 20px 60px; }
h1 { font-size: 22px; margin: 0 0 6px; }
.meta { color: #6b7280; font-size: 13px; margin-bottom: 18px;
        border-bottom: 1px solid #e5e7eb; padding-bottom: 12px; }
.q { margin: 0 0 16px; padding: 0 0 14px; border-bottom: 1px dashed #e5e7eb;
     break-inside: avoid; page-break-inside: avoid; }
.qt { font-size: 15px; }
.qno { color: #6b7280; margin-right: 6px; }
.qtype { display: inline-block; font-size: 11px; padding: 1px 6px; margin-right: 8px;
         border: 1px solid #cbd5e1; border-radius: 4px; color: #475569; vertical-align: 2px; }
.opts { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 18px; margin: 8px 0 0 4px; }
.opt { font-size: 14px; }
.ans { margin-top: 8px; color: #0a7d32; font-size: 14px; background: #f0fdf4;
       border-left: 3px solid #22c55e; padding: 4px 10px; border-radius: 3px; }
.answer-lines { height: 84px; margin-top: 8px; border-bottom: 1px solid #d1d5db; }
.answer-lines.sm { height: 30px; }
.qimg { display: block; max-width: 100%; max-height: 340px; margin: 8px 0; }
.img-missing { color: #b91c1c; font-size: 12px; }
.foot { margin-top: 26px; color: #9ca3af; font-size: 12px; text-align: center; }
@media print {
  body { padding: 0; max-width: none; }
  .q { break-inside: avoid; }
}
"""


def _doc_html(title: str, subtitle: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>{CSS}</style></head>
<body>
<h1>{_esc(title)}</h1>
<div class="meta">{subtitle}</div>
{body}
<div class="foot">由「刷题软件」导出 · {time.strftime('%Y-%m-%d %H:%M')}</div>
</body></html>"""


def _safe_filename(name: str) -> str:
    bad = '\\/:*?"<>|\r\n\t'
    out = "".join("_" if c in bad else c for c in str(name or "")).strip()
    return out[:80] or "导出"


def _stamp():
    return time.strftime("%Y%m%d_%H%M")


# ---------------------------------------------------------------- 对外入口

def export_bank(subject: str, questions, fmt: str = "html", with_answers: bool = True,
                title: str = None):
    """题库导出 → (bytes, filename, content_type)"""
    title = title or f"{subject} · 题库"
    n = len(questions)
    if fmt == "md":
        lines = [f"# {title}", "", f"共 {n} 题，导出于 {time.strftime('%Y-%m-%d %H:%M')}", ""]
        for i, q in enumerate(questions, 1):
            lines.append(question_md(q, i, with_answers))
        text = "\n".join(lines) + "\n"
        return text.encode("utf-8"), f"{_safe_filename(subject)}_题库_{_stamp()}.md", "text/markdown; charset=utf-8"

    body = "".join(question_html(q, i, with_answers) for i, q in enumerate(questions, 1))
    sub = f"共 {n} 题 · {'含答案解析' if with_answers else '不含答案（学生用）'} · 导出于 {time.strftime('%Y-%m-%d %H:%M')}"
    html = _doc_html(title, sub, body)
    return html.encode("utf-8"), f"{_safe_filename(subject)}_题库_{_stamp()}.html", "text/html; charset=utf-8"


def export_paper(subject: str, questions, fmt: str = "html", with_answers: bool = False,
                 title: str = None, note: str = ""):
    """试卷导出（学生版/教师版）"""
    title = title or f"{subject} · 模拟试卷"
    if fmt == "md":
        lines = [f"# {title}", "", f"{'教师版（含答案）' if with_answers else '学生版'}" + (f" · {note}" if note else ""), ""]
        for i, q in enumerate(questions, 1):
            lines.append(question_md(q, i, with_answers))
        text = "\n".join(lines) + "\n"
        return text.encode("utf-8"), f"{_safe_filename(subject)}_试卷_{_stamp()}.md", "text/markdown; charset=utf-8"

    body = "".join(question_html(q, i, with_answers) for i, q in enumerate(questions, 1))
    sub = (f"{'教师版（含答案）' if with_answers else '学生版'} · 共 {len(questions)} 题"
           + (f" · {note}" if note else "") + f" · 导出于 {time.strftime('%Y-%m-%d %H:%M')}")
    html = _doc_html(title, sub, body)
    suffix = "试卷_教师版" if with_answers else "试卷_学生版"
    return html.encode("utf-8"), f"{_safe_filename(subject)}_{suffix}_{_stamp()}.html", "text/html; charset=utf-8"


def export_wrong(entries, fmt: str = "html", with_answers: bool = True, title: str = "错题本"):
    """错题本导出；entries 是 Question 列表"""
    if fmt == "md":
        lines = [f"# {title}", "", f"共 {len(entries)} 题，导出于 {time.strftime('%Y-%m-%d %H:%M')}", ""]
        for i, q in enumerate(entries, 1):
            lines.append(f"**{i}. 【{q.subject}】**")
            lines.append(question_md(q, i, with_answers))
        text = "\n".join(lines) + "\n"
        return text.encode("utf-8"), f"{_safe_filename(title)}_{_stamp()}.md", "text/markdown; charset=utf-8"

    parts = []
    for i, q in enumerate(entries, 1):
        parts.append(f'<div class="q"><div class="qt"><span class="qno">{i}.</span>'
                     f'<span class="qtype">{_esc(q.subject)}</span></div>'
                     f'{question_html(q, i, with_answers)}</div>')
    sub = f"共 {len(entries)} 题 · 导出于 {time.strftime('%Y-%m-%d %H:%M')}"
    html = _doc_html(title, sub, "".join(parts))
    return html.encode("utf-8"), f"{_safe_filename(title)}_{_stamp()}.html", "text/html; charset=utf-8"
