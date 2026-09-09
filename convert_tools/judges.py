# -*- coding: utf-8 -*-
"""judge 插件自动发现与加载注册表
================================

每次调用 list_judges() 都会重新扫描本目录（convert_tools/）下的
convert*.py 转换脚本，judge 的文件名（不含 .py）即其 id；
脚本数量实时反映目录内容（新增/删除脚本后无需改代码）。

每个 judge 插件需提供：
    parse(text) -> list[Question]    # 解析原始文本为题库对象（仅含可导入的）
    render(questions) -> str         # 生成 text_converted.txt 排版文本

可选元数据（在插件模块内定义）：
    JUDGE_DESC = "一句话说明"            # 取不到则用模块 docstring 首行
    JUDGE_NAME = "显示名"                # 缺省用文件名 stem
    JUDGE_HIDDEN = True                 # 从默认列表隐藏（文件保留，可单独运行）
    JUDGE_ORDER = int                   # 排序（越小越靠前），缺省按文件名
"""

import importlib.util
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_EXCLUDED = {"judges.py", "__init__.py"}
_LOADED = {}


def _candidate_files():
    """扫描 convert*.py（judges.py 等自身排除；_ 开头为私有模块不参与）"""
    names = []
    for name in os.listdir(BASE):
        if not name.endswith(".py"):
            continue
        if name in _EXCLUDED or name.startswith("_"):
            continue
        if name.startswith("convert"):
            names.append(name)
    return sorted(names)


def _load(stem, path):
    """按文件路径加载/复用插件模块"""
    if stem in _LOADED:
        return _LOADED[stem]
    spec = importlib.util.spec_from_file_location(f"ct_judges_{stem}", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        print(f"[judges] 加载失败: {stem} ({e})")
        return None
    if not (callable(getattr(mod, "parse", None)) and callable(getattr(mod, "render", None))):
        print(f"[judges] {stem} 缺少 parse/render 接口，已跳过")
        return None
    _LOADED[stem] = mod
    return mod


def list_judges(include_hidden: bool = False):
    """
    返回 [{id, name, desc, order, hidden, parse, render}]，
    按 (JUDGE_ORDER, 文件名) 排序；默认过滤 JUDGE_HIDDEN=True 的规则。
    """
    result = []
    for name in _candidate_files():
        stem = name[:-3]
        mod = _load(stem, os.path.join(BASE, name))
        if mod is None:
            continue
        desc = getattr(mod, "JUDGE_DESC", "") or ""
        if not desc:
            doc = (getattr(mod, "__doc__", "") or "").strip().splitlines()
            desc = doc[0] if doc else stem
        hidden = bool(getattr(mod, "JUDGE_HIDDEN", False))
        if hidden and not include_hidden:
            continue
        result.append({
            "id": stem,
            "name": getattr(mod, "JUDGE_NAME", "") or stem,  # 显示名
            "desc": desc,
            "order": getattr(mod, "JUDGE_ORDER", None),
            "hidden": hidden,
            "echo_raw": bool(getattr(mod, "ECHO_RAW", False)),  # 直通 judge：输出=原始输入
            "parse": mod.parse,
            "render": mod.render,
        })
    result.sort(key=lambda j: (j["order"] if j["order"] is not None else 10 ** 9, j["id"]))
    return result


def get_judge(judge_id):
    """按文件名（id）取可见 judge；隐藏规则不返回（防误选），找不到返回 None"""
    for j in list_judges():
        if j["id"] == judge_id:
            return j
    return None


if __name__ == "__main__":
    js = list_judges(include_hidden=True)
    hidden_n = sum(1 for j in js if j["hidden"])
    print(f"共 {len(js)} 个转换规则（judge，含隐藏 {hidden_n} 个）：")
    for j in js:
        tag = "（隐藏）" if j["hidden"] else ""
        print(f"  - {j['id']} [{j['name']}]{tag}: {j['desc']}")
