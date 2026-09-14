# -*- coding: utf-8 -*-
"""
Android 入口（Chaquopy）
========================
由 MainActivity 调用：

    entry.start(home) -> int(端口)

流程：
1. 设置 ``SHUATI_HOME = home``（应用私有目录，PyApplication 的 filesDir）；
2. 幂等种子复制：把随包只读资源 ``seed/`` 下的
   ``data/*.json``（题库）、``pictures/**``（图片）、``bank_remote.json``（远程题库配置）
   复制进 HOME —— **只补缺失文件，绝不覆盖**用户已有数据；
3. 选一个空闲端口，在后台线程里跑 ``webui_server.start_server``（阻塞），
   就绪后把端口返回给 Java，由 WebView 打开 ``http://127.0.0.1:<port>/``。

桌面端不会走到这里（仍用 launcher.py / webui_server.py）。
"""

import json
import os
import shutil
import socket
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(_HERE, "seed")
SEED_VERSION_FILE = os.path.join(SEED_DIR, "seed_version.json")

_started_lock = threading.Lock()
_started_port = None


# ---------------------------------------------------------------- 种子 ----------------------------------------------------------------

def _copy_tree_missing(src, dst):
    """递归复制 src → dst，已存在的文件不覆盖"""
    copied = 0
    for dirpath, _dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in filenames:
            s = os.path.join(dirpath, name)
            d = os.path.join(target_dir, name)
            if os.path.exists(d):
                continue
            try:
                shutil.copy2(s, d)
                copied += 1
            except OSError:
                pass
    return copied


def _seed_version():
    try:
        with open(SEED_VERSION_FILE, "r", encoding="utf-8") as f:
            return str(json.load(f).get("seed_version") or "")
    except (OSError, ValueError):
        return ""


def ensure_home(home: str) -> dict:
    """设置 HOME、建目录、幂等种子复制；返回统计信息（便于日志/设置页展示）"""
    home = os.path.abspath(home)
    os.environ["SHUATI_HOME"] = home
    for sub in ("data", "pictures", "reports", "backups"):
        os.makedirs(os.path.join(home, sub), exist_ok=True)

    stamp_file = os.path.join(home, ".seed_version")
    want = _seed_version()
    have = ""
    if os.path.isfile(stamp_file):
        try:
            with open(stamp_file, "r", encoding="utf-8") as f:
                have = f.read().strip()
        except OSError:
            have = ""

    copied = 0
    if want and want != have:
        copied += _copy_tree_missing(os.path.join(SEED_DIR, "data"), os.path.join(home, "data"))
        copied += _copy_tree_missing(os.path.join(SEED_DIR, "pictures"), os.path.join(home, "pictures"))
        seed_cfg = os.path.join(SEED_DIR, "bank_remote.json")
        home_cfg = os.path.join(home, "bank_remote.json")
        if os.path.isfile(seed_cfg) and not os.path.exists(home_cfg):
            try:
                shutil.copy2(seed_cfg, home_cfg)
                copied += 1
            except OSError:
                pass
        elif os.path.isfile(seed_cfg) and os.path.isfile(home_cfg):
            # 老安装升级时：种子里的 bank_remote.json 可能新增了 gitee 镜像块，
            # 但本地配置是用户/上次安装留下的（不会被覆盖）。镜像地址属于“下载源偏好”
            # 而非个人数据，因此这里只做增量合并：本地没有 gitee 时补上，其余字段一律不动。
            try:
                with open(seed_cfg, "r", encoding="utf-8") as f:
                    seed = json.load(f)
                with open(home_cfg, "r", encoding="utf-8") as f:
                    cur = json.load(f)
                if isinstance(seed, dict) and isinstance(cur, dict):
                    changed = False
                    if seed.get("gitee") and not cur.get("gitee"):
                        cur["gitee"] = seed["gitee"]
                        changed = True
                    if changed:
                        with open(home_cfg, "w", encoding="utf-8") as f:
                            json.dump(cur, f, ensure_ascii=False, indent=2)
            except (OSError, ValueError):
                pass
        try:
            with open(stamp_file, "w", encoding="utf-8") as f:
                f.write(want)
        except OSError:
            pass
    return {"home": home, "seed_version": want, "copied": copied}


# ---------------------------------------------------------------- 服务 ----------------------------------------------------------------

def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _serve(port: int):
    import webui_server
    webui_server.start_server(host="127.0.0.1", port=port, open_browser=False)


def start(home: str, app_version: str = "") -> int:
    """启动本地服务并返回端口号（供 Java/WebView 使用）

    app_version：由 MainActivity 传入的 APK 版本号（BuildConfig.VERSION_NAME），
    写入环境变量供 /api/app/info 在设置页展示。
    """
    global _started_port
    with _started_lock:
        if _started_port:
            return _started_port

        info = ensure_home(home)
        os.environ["SHUATI_APP_VERSION"] = str(app_version or "")
        # 确保能 import 到打包进来的项目模块（APP_DIR 即本文件所在目录）
        if _HERE not in sys.path:
            sys.path.insert(0, _HERE)

        port = _free_port()
        t = threading.Thread(target=_serve, args=(port,), name="shuati-webui", daemon=True)
        t.start()
        if not _wait_ready(port):
            raise RuntimeError(f"本地服务启动超时（端口 {port}）")
        _started_port = port
        print(f"[shuati] HOME={info['home']} seed={info['seed_version']} copied={info['copied']} port={port}")
        return port


def version() -> str:
    """应用/数据版本信息（供设置页或日志显示）"""
    info = {}
    try:
        with open(os.path.join(SEED_DIR, "seed_version.json"), "r", encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        pass
    return json.dumps({
        "app_version": os.environ.get("SHUATI_APP_VERSION", ""),
        "seed_version": info.get("seed_version", ""),
        "generated_at": info.get("generated_at", ""),
        "home": os.environ.get("SHUATI_HOME", ""),
        "python": sys.version.split()[0],
    }, ensure_ascii=False)
