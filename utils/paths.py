# -*- coding: utf-8 -*-
"""
统一路径层（桌面 / Android 双形态）
====================================
- ``APP_DIR``：代码与只读资源所在目录（桌面 = 项目根；Android = Chaquopy 解包目录）。
- ``HOME``：**可写**数据根。桌面默认等于 ``APP_DIR``（与历史行为完全一致）；
  设置环境变量 ``SHUATI_HOME`` 时改为该目录（Android 设为应用私有 filesDir；
  也可用于桌面多档案 / 测试隔离）。
- 运行时可写路径全部由 ``HOME`` 派生：data / pictures / reports / backups / 同步状态文件。
- 只读资源路径始终由 ``APP_DIR`` 派生：webui / convert_tools。
- 远程题库配置 ``bank_remote.json``：代码目录优先（维护者/随包种子提供），HOME 兜底（手机端可写）。
"""

import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.abspath(os.environ.get("SHUATI_HOME") or APP_DIR)

# ---- 可写数据（HOME 下）----
DATA_DIR = os.path.join(HOME, "data")
PICTURES_DIR = os.path.join(HOME, "pictures")
REPORTS_DIR = os.path.join(HOME, "reports")
BACKUPS_DIR = os.path.join(HOME, "backups")
STATE_FILE = os.path.join(HOME, ".bank_sync_state.json")

# ---- 只读资源（APP_DIR 下）----
WEBUI_DIR = os.path.join(APP_DIR, "webui")
CONVERT_TOOLS_DIR = os.path.join(APP_DIR, "convert_tools")

_APP_REMOTE_CONFIG = os.path.join(APP_DIR, "bank_remote.json")
_HOME_REMOTE_CONFIG = os.path.join(HOME, "bank_remote.json")

MANIFEST_NAME = "data_manifest.json"


def remote_config_file() -> str:
    """远程题库配置路径：APP_DIR 优先，HOME 兜底"""
    if os.path.isfile(_APP_REMOTE_CONFIG):
        return _APP_REMOTE_CONFIG
    return _HOME_REMOTE_CONFIG


# 保持常量形式，便于既有代码/自检猴子补丁继续使用
REMOTE_CONFIG_FILE = remote_config_file()


def manifest_path() -> str:
    """题库同步清单路径（维护者在代码目录生成；Android 只读环境不需要生成）"""
    return os.path.join(APP_DIR, MANIFEST_NAME)


def ensure_writable_dirs():
    """确保 HOME 下四个可写目录存在（Android 首启用）"""
    for p in (DATA_DIR, PICTURES_DIR, REPORTS_DIR, BACKUPS_DIR):
        os.makedirs(p, exist_ok=True)


def describe() -> dict:
    """给日志 / 设置页展示的路径概览"""
    return {
        "APP_DIR": APP_DIR,
        "HOME": HOME,
        "SHUATI_HOME_ENV": os.environ.get("SHUATI_HOME", ""),
        "DATA_DIR": DATA_DIR,
        "PICTURES_DIR": PICTURES_DIR,
        "REPORTS_DIR": REPORTS_DIR,
        "BACKUPS_DIR": BACKUPS_DIR,
        "STATE_FILE": STATE_FILE,
        "REMOTE_CONFIG_FILE": REMOTE_CONFIG_FILE,
    }
