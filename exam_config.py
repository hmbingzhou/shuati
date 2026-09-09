# -*- coding: utf-8 -*-
"""
模拟考试配置
============
这里是【每科每种题型抽多少题】以及【抽题权重】的修改入口。
改了之后刷新页面即可（网页每次读取）。

示例：想给 Java 单独定制一套，就在 SUBJECT_COMPOSITION 里加：
    SUBJECT_COMPOSITION = {"Java": {"判断题": 3, "单选题": 8, "多选题": 4, "填空题": 3, "简答题": 0}}
"""

# 各科目统一的默认抽题数（没有单独配置时使用）
DEFAULT_COMPOSITION = {
    "判断题": 5,
    "单选题": 10,
    "多选题": 5,
    "填空题": 5,
    "简答题": 0,
}

# 需要按科目单独定制时在这里加（键=科目名，值=覆盖题型数，缺省题型回落到默认值）
SUBJECT_COMPOSITION = {
    # 示例（取消注释即可生效）：
    # "Java": {"判断题": 3, "单选题": 8, "多选题": 4, "填空题": 3, "简答题": 0},
}

# 抽题权重（加权不放回抽样）：
#   未考过的题 + WEIGHT_NEVER_EXAM（比错题本略大）
#   在错题本中的题 + WEIGHT_IN_WRONG（略小）
#   两者可叠加；普通题权重 = WEIGHT_BASE
WEIGHT_BASE = 1
WEIGHT_NEVER_EXAM = 5
WEIGHT_IN_WRONG = 4


def composition_for(subject: str) -> dict:
    """返回某科实际使用的抽题数（科目定制覆盖默认，缺省题型取默认）"""
    cfg = dict(DEFAULT_COMPOSITION)
    override = SUBJECT_COMPOSITION.get(subject or "", {}) or {}
    cfg.update(override)
    return cfg
