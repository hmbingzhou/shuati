# -*- coding: utf-8 -*-
"""judge 插件自动发现与加载注册表

每次调用 list_judges() 都会重新扫描本目录（convert_tools/）下的
convert*.py 转换脚本，judge 的文件名（不含 .py）即其 id 与显示名；
脚本数量实时反映目录内容（新增/删除脚本后无需改代码）。

每个 judge 插件需提供：
    parse(text) -> list[Question]    # 解析原始文本为题库对象（仅含可导入的）
    render(questions) -> str         # 生成 text_converted.txt 排版文本
可选：
    JUDGE_DESC = "一句话说明"          # 取不到则用模块 docstring 首行
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
    """扫描 convert*.py（judges.py 等自身排除）"""
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


def list_judges():
    """返回 [{id, name, desc, parse, render}]，按文件名排序；每次调用实时扫描"""
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
        result.append({
            "id": stem,
            "name": stem,  # 文件名（去 .py）即名字
            "desc": desc,
            "echo_raw": bool(getattr(mod, "ECHO_RAW", False)),  # 直通 judge：输出=原始输入
            "parse": mod.parse,
            "render": mod.render,
        })
    return result


def get_judge(judge_id):
    """按文件名（id）取 judge，找不到返回 None"""
    for j in list_judges():
        if j["id"] == judge_id:
            return j
    return None


if __name__ == "__main__":
    js = list_judges()
    print(f"共 {len(js)} 个转换规则（judge）：")
    for j in js:
        print(f"  - {j['name']}: {j['desc']}")
