# -*- coding: utf-8 -*-
"""
构建期：生成 Android 工程的 Python 源码目录（单一真源，不复制业务代码进 git）
================================================================================
把「运行所需」的项目文件拷贝到 ``android/app/src/main/python``，并生成首启种子 ``seed/``：

    android/app/src/main/python/
        entry.py                  ← 由 android/entry.py 拷贝
        webui_server.py question_manager.py …（运行时模块）
        models/ utils/ convert_tools/
        webui/                    ← 静态前端（index.html/app.js/style.css/manifest/icons）
        seed/
            data/*.json           ← 题库（排除 records/wrong_book/recycle_bin/exams/brush_progress）
            pictures/**           ← 题目图片
            bank_remote.json      ← 远程题库配置（owner/repo/branch，优先取仓库现有配置）
            seed_version.json     ← 种子版本（变更时触发“只补缺失”的复制）

用法：
    python android/prepare_python_src.py            # 生成
    python android/prepare_python_src.py --check    # 只校验生成结果（构建脚本用）
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STAGING = os.path.join(HERE, "app", "src", "main", "python")
SEED = os.path.join(STAGING, "seed")

# 运行时需要的根级模块（终端版菜单/启动器不进 APK）
ROOT_MODULES = [
    "webui_server.py",
    "question_manager.py",
    "records.py",
    "exams.py",
    "exam_config.py",
    "recycle_bin.py",
    "archive_manager.py",
    "duplicate_finder.py",
    "reporter.py",
    "sync_bank.py",
]
PACKAGES = ["models", "utils", "convert_tools", "webui"]

USER_DATA_FILES = {"records.json", "wrong_book.json", "recycle_bin.json",
                   "exams.json", "brush_progress.json"}

EXCLUDE_NAMES = {"__pycache__", ".git", ".pytest_cache"}
EXCLUDE_SUFFIX = (".pyc", ".pyo")


def _log(msg):
    print(msg)


def _copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src, dst, skip_names=(), skip_suffix=()):
    """递归复制；返回复制成功的文件数"""
    n = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip_names]
        rel = os.path.relpath(dirpath, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in filenames:
            if name in skip_names or name.endswith(skip_suffix):
                continue
            shutil.copy2(os.path.join(dirpath, name), os.path.join(target_dir, name))
            n += 1
    return n


def _git_default_branch_remote():
    """优先读仓库已有的 bank_remote.json；否则尝试 git remote origin"""
    cfg = os.path.join(ROOT, "bank_remote.json")
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("owner") and data.get("repo"):
                data.setdefault("branch", "main")
                return data
        except (OSError, ValueError):
            pass
    try:
        import subprocess
        out = subprocess.run(["git", "-C", ROOT, "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10)
        url = (out.stdout or "").strip()
        m = re.search(r"[:/]([^/:\s]+)/([^/\s]+?)(?:\.git)?$", url)
        if m:
            return {"owner": m.group(1), "repo": m.group(2), "branch": "main",
                    "sources": ["jsdelivr", "github"]}
    except Exception:
        pass
    return {"owner": "", "repo": "shuati", "branch": "main"}


def _seed_stamp():
    """种子版本：内容哈希（题库+图片+配置变化时自动变化）"""
    h = hashlib.sha256()
    data_dir = os.path.join(ROOT, "data")
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith(".json") or name in USER_DATA_FILES:
            continue
        h.update(name.encode("utf-8"))
        h.update(str(os.path.getsize(os.path.join(data_dir, name))).encode())
    pics = os.path.join(ROOT, "pictures")
    for dirpath, _d, files in os.walk(pics):
        for name in sorted(files):
            h.update(name.encode("utf-8"))
    cfg = _git_default_branch_remote()
    h.update(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()[:12]


def build(clean=True):
    if clean and os.path.isdir(STAGING):
        shutil.rmtree(STAGING, ignore_errors=True)
    os.makedirs(STAGING, exist_ok=True)

    # 1) 入口
    _copy_file(os.path.join(HERE, "entry.py"), os.path.join(STAGING, "entry.py"))

    # 2) 运行时模块
    missing = []
    for name in ROOT_MODULES:
        src = os.path.join(ROOT, name)
        if not os.path.isfile(src):
            missing.append(name)
            continue
        _copy_file(src, os.path.join(STAGING, name))
    for pkg in PACKAGES:
        src = os.path.join(ROOT, pkg)
        if not os.path.isdir(src):
            missing.append(pkg + "/")
            continue
        _copy_tree(src, os.path.join(STAGING, pkg),
                   skip_names=EXCLUDE_NAMES, skip_suffix=EXCLUDE_SUFFIX)
    if missing:
        raise SystemExit(f"缺少运行时文件：{missing}")

    # 3) 种子：题库（排除个人数据）
    data_src = os.path.join(ROOT, "data")
    os.makedirs(os.path.join(SEED, "data"), exist_ok=True)
    seed_files = 0
    for name in sorted(os.listdir(data_src)):
        if not name.endswith(".json") or name in USER_DATA_FILES or name.startswith("."):
            continue
        _copy_file(os.path.join(data_src, name), os.path.join(SEED, "data", name))
        seed_files += 1

    # 4) 种子：图片
    pics_src = os.path.join(ROOT, "pictures")
    pics_n = _copy_tree(pics_src, os.path.join(SEED, "pictures"),
                        skip_names=EXCLUDE_NAMES, skip_suffix=EXCLUDE_SUFFIX)

    # 5) 种子：远程题库配置 + 版本戳
    cfg = _git_default_branch_remote()
    if not cfg.get("owner"):
        _log("  ⚠️ 未识别到题库仓库 owner（请在仓库根放置 bank_remote.json），应用内“更新题库”将不可用")
    with open(os.path.join(SEED, "bank_remote.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    stamp = _seed_stamp()
    with open(os.path.join(SEED, "seed_version.json"), "w", encoding="utf-8") as f:
        json.dump({
            "seed_version": stamp,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "questions_files": seed_files,
            "pictures": pics_n,
        }, f, ensure_ascii=False, indent=2)

    size = sum(os.path.getsize(os.path.join(dp, fn))
               for dp, _d, fs in os.walk(STAGING) for fn in fs)
    _log(f"  ✓ 生成 {os.path.relpath(STAGING, ROOT)}：题库 {seed_files} 个、图片 {pics_n} 个、"
         f"合计 {size / 1048576:.2f} MB")
    _log(f"    远程题库配置：{cfg.get('owner')}/{cfg.get('repo')}@{cfg.get('branch')}  种子版本 {stamp}")
    return 0


def check():
    """校验 staging 是否完整（供 build_apk.ps1 调用）"""
    problems = []
    for rel in ["entry.py", "webui_server.py", "question_manager.py",
                "models/question.py", "utils/paths.py", "webui/index.html", "webui/app.js",
                "webui/manifest.webmanifest", "convert_tools/judges.py",
                "seed/bank_remote.json", "seed/seed_version.json"]:
        if not os.path.isfile(os.path.join(STAGING, rel.replace("/", os.sep))):
            problems.append(rel)
    data_dir = os.path.join(SEED, "data")
    bank = [f for f in os.listdir(data_dir) if f.endswith(".json")] if os.path.isdir(data_dir) else []
    if not bank:
        problems.append("seed/data/*.json（题库种子）")
    if problems:
        print("  ✗ staging 不完整：" + "，".join(problems))
        return 1
    print(f"  ✓ staging 校验通过：题库种子 {len(bank)} 个")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 Android Python 源码/种子目录")
    parser.add_argument("--check", action="store_true", help="只校验已生成结果")
    parser.add_argument("--no-clean", action="store_true", help="增量生成（默认先清空）")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if args.check:
        return check()
    _log("准备 Android Python 源码目录：")
    return build(clean=not args.no_clean)


if __name__ == "__main__":
    sys.exit(main())
