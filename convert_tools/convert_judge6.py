# -*- coding: utf-8 -*-
"""judge6 · 计算题（占位，待实现）

计算题规则暂未实现，仅保留编号与说明（进入批量导入后选择它，
预览会显示识别 0 道）。后续按与 judge1-5 一致的纯文本排版约定补齐：
    题干（可含图片文件名）

    答案（数字/表达式等，支持同一题列出多个可接受答案）

作为 convert_tools 的 judge 插件使用（文件名即 id）；也可直接运行。
"""

import os

BASE = os.path.dirname(os.path.abspath(__file__))
JUDGE_NAME = "计算题"
JUDGE_ORDER = 80
JUDGE_DESC = "计算题（待实现，暂不可转换；先占位保留编号）"


def parse(text):  # noqa: ARG001
    """占位：暂不解析，返回空列表"""
    return []


def render(questions):  # noqa: ARG001
    return ""


def main():
    print("计算题规则尚未实现（占位）。")


if __name__ == '__main__':
    main()
