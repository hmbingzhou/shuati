# -*- coding: utf-8 -*-
"""
数据存档（打包 / 恢复）
======================
- create_archive(): 把 data/ 下全部 JSON（题库、错题本、进度、回收站、正确率记录、考试记录）
  打包为 backups/存档_时间戳.zip，附 manifest.json。
- restore_archive(raw): 校验并解包 zip 到 data/，只允许 data 根目录 *.json，拒绝路径穿越等。
  恢复前由调用方先做一次自动备份。
"""

import datetime
import io
import json
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
BACKUP_DIR = os.path.join(ROOT, "backups")

MAX_ARCHIVE_BYTES = 200 * 1024 * 1024  # 200MB 上限
SAFE_NAME_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9_\-]+\.json$")


def _json_files():
    """data 目录下所有 json 文件名（根目录扁平）"""
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(f for f in os.listdir(DATA_DIR) if f.lower().endswith(".json"))


def _question_total(files):
    total = 0
    for f in files:
        p = os.path.join(DATA_DIR, f)
        try:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                total += len(data)
        except Exception:
            pass
    return total


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_now(prefix="restore_before"):
    """把当前 data 备份成一个 zip，返回文件名（用于导入前快照）"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = f"{prefix}_{_stamp()}.zip"
    path = os.path.join(BACKUP_DIR, name)
    _write_zip(path)
    return name


def _write_zip(path):
    files = _json_files()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(os.path.join(DATA_DIR, f), arcname=f)
        manifest = {
            "app": "shuati",
            "format": 1,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": files,
            "questions": _question_total(files),
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return files


def create_archive():
    """生成存档并保存到 backups/，返回 {name, files, questions}"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = f"存档_{_stamp()}.zip"
    path = os.path.join(BACKUP_DIR, name)
    files = _write_zip(path)
    return {"name": name, "files": len(files), "questions": _question_total(files)}


def read_archive_bytes(name):
    """按文件名读取备份目录里的 zip 字节（调用方负责文件名白名单）"""
    with open(os.path.join(BACKUP_DIR, name), "rb") as f:
        return f.read()


def safe_archive_name(name):
    """download/文件名校验：防路径穿越，仅允许备份目录内的 zip"""
    if not name or "/" in name or "\\" in name or ".." in name or not name.lower().endswith(".zip"):
        return False
    return os.path.isfile(os.path.join(BACKUP_DIR, name))


def restore_archive(raw: bytes) -> dict:
    """校验并恢复存档。返回 {restored:[文件名], questions}；非法内容抛 ValueError 且不改动文件"""
    if not raw or len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("存档为空或超过大小限制")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError("不是有效的 zip 存档")

    entries = []
    for info in zf.infolist():
        name = info.filename
        # 扁平、只允许 *.json、无路径穿越
        if name == "manifest.json":
            continue
        if "/" in name or "\\" in name or not name.endswith(".json"):
            continue
        base = os.path.basename(name)
        if base != name:
            continue
        if not SAFE_NAME_RE.match(base):
            raise ValueError(f"存档内含非法文件名: {name}")
        entries.append((name, info.file_size))

    if not entries:
        raise ValueError("存档里没有可恢复的题目数据")

    os.makedirs(DATA_DIR, exist_ok=True)
    restored = []
    for name, _size in entries:
        data = zf.read(name)
        # 校验是合法 UTF-8 JSON
        try:
            json.loads(data.decode("utf-8"))
        except Exception:
            raise ValueError(f"存档文件不是合法 JSON: {name}")
        with open(os.path.join(DATA_DIR, name), "wb") as fh:
            fh.write(data)
        restored.append(name)

    return {"restored": restored, "questions": _question_total(restored)}
