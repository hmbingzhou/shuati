# -*- coding: utf-8 -*-
"""
终端版批量导入界面（judge 转换）
================================
流程：由 menu.py 先选择 年级 -> 科目，再调用本模块。

界面内会：
1. 提示用户把待转换的原始文本保存到 convert_tools/text.txt（用文本编辑器）。
2. 动态扫描 convert_tools/ 下的 judge 转换脚本（数量与文件名实时读取），
   显示"共 N 个转换规则"，用户按编号选择。
3. 运行所选 judge：打印识别到的题目数量，并把转换结果写入
   convert_tools/text_converted.txt（不自动入库）。
"""

import os
import sys

# 项目根目录（本文件位于项目根目录）
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from convert_tools.judges import list_judges  # noqa: E402  (convert_tools 为隐式命名空间包)

# judges.BASE 即 convert_tools 目录
from convert_tools import judges as _judges_mod  # noqa: E402

TEXT_PATH = os.path.join(_judges_mod.BASE, "text.txt")
CONVERTED_PATH = os.path.join(_judges_mod.BASE, "text_converted.txt")

_BACK = {"0", "back", "menu", "esc", "exit"}


def _print_judges():
    """每次进入选择界面都重新扫描，返回 [{id,name,desc}]"""
    js = list_judges()
    if not js:
        print("  ⚠️ 没有找到任何 judge 转换脚本（convert_tools/ 下 convert*.py）。")
        return []
    print(f"\n  共 {len(js)} 个转换规则（judge）：")
    for i, j in enumerate(js, 1):
        print(f"    {i}. {j['name']} —— {j['desc']}")
    return js


def run_import_screen(grade: str, subject: str):
    """批量导入主界面（已选定 年级/科目）"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("\n" + "=" * 56)
    print("           批量导入题目 · judge 转换")
    print("=" * 56)
    print(f"  范围：【{grade}】{subject}")
    print()

    while True:
        print("=" * 56)
        print("  第 1 步：把待导入的原始文本用文本编辑器保存到：")
        print(f"    {TEXT_PATH}")
        print("  第 2 步：在本界面选择转换规则（judge）并回车。")
        print("  输入 0 / back 返回上级。")
        print("=" * 56)

        try:
            cmd = input("\n按回车继续（确认 text.txt 已准备好），或输入 0 返回: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if cmd.lower() in _BACK or cmd == "0":
            return

        if not os.path.exists(TEXT_PATH):
            print(f"\n  ⚠️ 未找到 {TEXT_PATH}")
            print("  请先用文本编辑器把原始文本粘贴进去再继续。")
            continue

        with open(TEXT_PATH, "r", encoding="utf-8") as f:
            raw_text = f.read()
        if not raw_text.strip():
            print("  ⚠️ text.txt 内容为空，请先粘贴原始文本。")
            continue

        js = _print_judges()
        if not js:
            return

        try:
            choice = input("\n请选择转换规则编号: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if choice.lower() in _BACK:
            continue
        try:
            idx = int(choice)
        except ValueError:
            print("  无效输入。")
            continue
        if not (1 <= idx <= len(js)):
            print("  无效编号。")
            continue

        judge = js[idx - 1]
        try:
            questions = judge["parse"](raw_text)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 解析出错：{e}")
            continue

        output = raw_text if judge.get("echo_raw") else judge["render"](questions)
        with open(CONVERTED_PATH, "w", encoding="utf-8") as f:
            f.write(output)

        print(f"\n  ✓ 使用转换规则 [{judge['name']}]：识别到 {len(questions)} 道题。")
        print(f"  转换结果已写入：\n    {CONVERTED_PATH}")
        print("  （终端版不自动入库；可打开 text_converted.txt 检查后，")
        print("    再用网页版『批量导入』直接录入，或用逐题录入添加。）")

        try:
            again = input("\n  继续转下一批？(回车继续 / 0 返回): ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if again.lower() in _BACK or again == "0":
            return


if __name__ == "__main__":
    # 便于单独调试：python batch_import.py "大一上" "Java"
    _grade = sys.argv[1] if len(sys.argv) > 1 else "大一上"
    _subject = sys.argv[2] if len(sys.argv) > 2 else "Java"
    run_import_screen(_grade, _subject)
