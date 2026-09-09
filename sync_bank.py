# -*- coding: utf-8 -*-
"""
题库远程同步器（GitHub）
========================
让每个使用者都能从 GitHub 远程**下载 / 更新题库**，不需要懂 git。

原理
----
1. 维护者把「程序代码 + 题库 data/*.json + 题目图片 pictures/」推到自己的 GitHub 仓库，
   并在仓库根目录放一个清单文件 `data_manifest.json`（本文件的索引 + 每个文件的 sha256）。
2. 使用者运行本工具（或在网页版/终端版里点「更新题库」），程序会：
   - 读取远程 `data_manifest.json`，和本地文件逐一对 sha256，
   - 只下载「新增 / 有变化」的文件（先下载校验，全部成功后才写盘），
   - 更新前自动把旧文件备份到 backups/sync_backup_时间戳/，
   - 远程已下架的题库文件会提示并删除（仅当本地没改过）。

远程仓库从哪来（按优先级）：
1. 本目录下的 bank_remote.json（配置 owner/repo/branch，适合发给“没装 git、用 zip 包”的用户）；
2. 从 git 的 remote origin 自动识别（使用者 `git clone` 来的就自动生效，无需配置）；
3. 本文件顶部的 DEFAULT_OWNER / DEFAULT_REPO / DEFAULT_BRANCH 兜底。

下载源（国内访问 GitHub 慢时自动切换）：
- 首选 jsDelivr CDN（github 内容加速，大陆一般可直连）
- 备用 raw.githubusercontent.com（GitHub 原始文件地址）

命令行用法（在项目根目录）:
    python sync_bank.py info                       # 查看当前远程配置
    python sync_bank.py check                      # 检查是否有题库更新
    python sync_bank.py update                     # 下载并应用更新（自动备份）
    python sync_bank.py setup <owner> <repo> [branch]   # 写 bank_remote.json
    python sync_bank.py build-manifest             # 【维护者】重新生成 data_manifest.json 并显示提交提示

依赖：仅 Python 标准库，无第三方包。
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- 常量 ----------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PICTURES_DIR = os.path.join(BASE_DIR, "pictures")
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")
REMOTE_CONFIG_FILE = os.path.join(BASE_DIR, "bank_remote.json")   # 可选：手动指定远程仓库
MANIFEST_NAME = "data_manifest.json"                              # 仓库根目录的清单文件名
STATE_FILE = os.path.join(BASE_DIR, ".bank_sync_state.json")      # 本地“上次同步结果”，勿提交

# 需要图片的科目在 pictures/ 目录，题库数据在 data/ 目录 —— 两者都属于“题库”，一起同步
SYNC_DIRS = ("data", "pictures")

# data/ 里这些是“用户自己的数据”（错题本/记录/回收站…），既不会上传也不会被远程覆盖
USER_DATA_FILES = {
    "records.json", "wrong_book.json", "recycle_bin.json",
    "exams.json", "brush_progress.json",
}

# 兜底默认值（仅当上面两种方式都没配置时使用）→ 改成你自己的 GitHub 仓库
DEFAULT_OWNER = "你的GitHub用户名"
DEFAULT_REPO = "shuati"
DEFAULT_BRANCH = "main"

# 下载源顺序：0 = 优先（国内快），可被 bank_remote.json 的 "sources" 覆盖
SOURCE_DEFS = [
    {"name": "jsdelivr",
     "desc": "jsDelivr CDN（大陆一般可直连，需仓库为 public）",
     "fmt": "https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{path}"},
    {"name": "github",
     "desc": "GitHub 原始地址（需要能访问 github.com）",
     "fmt": "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"},
]

CONNECT_TIMEOUT = 6      # 连接超时（秒）
READ_TIMEOUT = 20        # 读取超时（秒）
MAX_BACKUPS = 5          # backups/sync_backup_* 最多保留几份
USER_AGENT = "Mozilla/5.0 (ShuatiBankSync/1.0)"

_apply_lock = threading.Lock()


# ---------------------------------------------------------------- 异常 ----------------------------------------------------------------

class SyncError(Exception):
    """同步过程中可预期的错误（消息可直接展示给用户）"""


# ---------------------------------------------------------------- 基础工具 ----------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# 需要“换行规范化”再算 hash 的文本类型。
# 仓库按 .gitattributes 以 LF 存储/检出；若本机文件是 CRLF，必须先去 CR 再哈希，
# 否则本机算出的 sha256 永远和远程（LF）对不上。
CANONICAL_TEXT_EXTS = {".json", ".md", ".txt", ".py", ".js", ".css", ".html", ".csv"}


def _canonical_bytes(data: bytes) -> bytes:
    """把文本内容规范化为 LF（与 git eol=lf 一致）；非 UTF-8/二进制文件原样返回"""
    ext = ""
    try:
        text = data.decode("utf-8")
        if "\r\n" in text or text.startswith("\r"):
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text.encode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return data


def _sha256_file(path: str):
    """文件 sha256：扩展名在 CANONICAL_TEXT_EXTS 里的先规范化为 LF 再哈希"""
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    if ext in CANONICAL_TEXT_EXTS:
        data = _canonical_bytes(data)
    return _sha256_bytes(data)


def _ts() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _quote_relpath(rel: str) -> str:
    """把清单里的相对路径（data/C语言.json）转成 URL 安全的每段编码"""
    return "/".join(urllib.parse.quote(seg) for seg in rel.split("/"))


def _load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------- 远程仓库识别 ----------------------------------------------------------------

def _parse_github_url(url: str):
    """从各种形式的 GitHub 地址里解析 (owner, repo)，失败返回 None"""
    url = (url or "").strip()
    if not url:
        return None
    if url.endswith(".git"):
        url = url[:-4]
    # https://github.com/owner/repo  或  https://github.com/owner/repo.git
    # git@github.com:owner/repo      或  ssh://git@github.com/owner/repo
    m = re.search(r"[:/]([^/:\s]+)/([^/\s]+?)(?:\.git)?\s*$", url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if not owner or not repo or owner.lower() in ("github.com", "github"):
        return None
    return owner, repo


def _git_origin():
    """从本地 git remote 读取 origin 地址（使用者 clone 来的即可自动识别）"""
    try:
        out = subprocess.run(
            ["git", "-C", BASE_DIR, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _resolve_remote():
    """
    返回 (owner, repo, branch, sources, 来源说明)。
    找不到可用配置时抛 SyncError，消息里给出配置方法。
    """
    cfg = _load_json(REMOTE_CONFIG_FILE)
    if cfg and isinstance(cfg, dict):
        owner = (cfg.get("owner") or "").strip()
        repo = (cfg.get("repo") or "").strip()
        if owner and repo and owner != DEFAULT_OWNER:
            branch = (cfg.get("branch") or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
            sources = cfg.get("sources") or [s["name"] for s in SOURCE_DEFS]
            return owner, repo, branch, sources, "bank_remote.json"
        # 文件存在但没填好 → 继续尝试其它来源
    origin = _git_origin()
    parsed = _parse_github_url(origin) if origin else None
    if parsed:
        owner, repo = parsed
        if owner != DEFAULT_OWNER:
            return owner, repo, DEFAULT_BRANCH, [s["name"] for s in SOURCE_DEFS], "git-origin"

    if DEFAULT_OWNER and DEFAULT_OWNER not in ("你的GitHub用户名", ""):
        return (DEFAULT_OWNER.strip(), DEFAULT_REPO.strip(), DEFAULT_BRANCH,
                [s["name"] for s in SOURCE_DEFS], "default")

    raise SyncError(
        "还没有配置题库的远程仓库。\n"
        f"  方式一（推荐）：用 git clone 下载本项目，本工具会自动读取仓库地址；\n"
        f"  方式二：在项目根目录运行  python sync_bank.py setup <你的GitHub用户名> <仓库名>\n"
        f"  方式三：手动创建 {os.path.basename(REMOTE_CONFIG_FILE)}，内容形如：\n"
        f'    {{"owner": "你的GitHub用户名", "repo": "{DEFAULT_REPO}", "branch": "{DEFAULT_BRANCH}"}}'
    )


def _source_urls(owner, repo, branch, sources, relpath):
    """按 sources 顺序生成同一文件的所有候选 URL"""
    quoted = _quote_relpath(relpath)
    urls = []
    for s in SOURCE_DEFS:
        if s["name"] not in sources:
            continue
        urls.append(s["fmt"].format(owner=owner, repo=repo, branch=branch, path=quoted))
    return urls


# ---------------------------------------------------------------- 网络 ----------------------------------------------------------------

def _http_get(urls, timeout=READ_TIMEOUT):
    """逐个候选 URL 尝试下载，返回 (bytes, 最终使用的url)。全部失败抛 SyncError。"""
    errors = []
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), url
        except urllib.error.HTTPError as e:
            errors.append(f"{url} -> HTTP {e.code}")
            if e.code == 404:
                # 404 说明该源上不存在；继续试下一个源
                continue
        except Exception as e:
            errors.append(f"{url} -> {type(e).__name__}: {e}")
    raise SyncError("下载失败：" + "；".join(errors))


def fetch_manifest(remote=None):
    """从远程下载 data_manifest.json，返回解析后的 dict"""
    owner, repo, branch, sources, _src = remote or _resolve_remote()
    manifest_urls = _source_urls(owner, repo, branch, sources, MANIFEST_NAME)
    raw, _used = _http_get(manifest_urls)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise SyncError("远程清单不是合法的 JSON，可能仓库内容异常。")
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        raise SyncError(
            f"远程清单格式不对（缺少 files 字段）。请让维护者在仓库根目录运行一次\n"
            f"  python sync_bank.py build-manifest\n并提交生成的 {MANIFEST_NAME}。"
        )
    data["files"] = {str(k): str(v) for k, v in files.items() if v}
    data.setdefault("generated_at", "")
    return data


# ---------------------------------------------------------------- 本地清单/状态 ----------------------------------------------------------------

def _walk_sync_files():
    """遍历 data/ 与 pictures/ 下应纳入题库同步的文件，返回 {相对路径: 绝对路径}"""
    out = {}
    for root_dir in SYNC_DIRS:
        base = os.path.join(BASE_DIR, root_dir)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                abs_path = os.path.join(dirpath, name)
                rel = os.path.relpath(abs_path, BASE_DIR).replace(os.sep, "/")
                if root_dir == "data" and name in USER_DATA_FILES:
                    continue  # 个人数据不进题库清单
                out[rel] = abs_path
    return out


def build_manifest(target=None, verbose=False):
    """【维护者】生成 data_manifest.json：记录 data/ 与 pictures/ 全部题库文件的 sha256"""
    files = {rel: _sha256_file(p) for rel, p in sorted(_walk_sync_files().items())}
    manifest = {
        "format": 1,
        "generated_at": _ts(),
        "note": "题库同步清单。由「python sync_bank.py build-manifest」自动生成，请随题库一起提交到 GitHub。",
        "files": files,
    }
    target = target or os.path.join(BASE_DIR, MANIFEST_NAME)
    _write_json(target, manifest)
    if verbose:
        print(f"  ✓ 已生成 {os.path.relpath(target, BASE_DIR)}")
        print(f"    共收录 {len(files)} 个文件（data 题库 + pictures 图片）")
        _print_commit_hint()
    return manifest


def _print_commit_hint():
    print("\n  接下来请提交并推送（在项目根目录）：")
    print("      git add data data_manifest.json pictures")
    print("      git commit -m \"更新题库\"")
    print("      git push")
    print("  使用者之后在软件里点「检查更新/更新题库」即可拉取。")


def _state_sha(manifest: dict) -> str:
    canon = json.dumps({"files": manifest.get("files") or {}},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canon.encode("utf-8"))


def _read_state():
    return _load_json(STATE_FILE, {})


def _write_state(manifest: dict):
    _write_json(STATE_FILE, {
        "manifest_sha": _state_sha(manifest),
        "updated_at": _ts(),
        "files": dict(manifest.get("files") or {}),
    })


def local_sha(rel: str):
    """读本地文件 sha256，不存在返回 None"""
    path = os.path.join(BASE_DIR, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        return None
    try:
        return _sha256_file(path)
    except OSError:
        return None


# ---------------------------------------------------------------- 更新计划 ----------------------------------------------------------------

def build_plan(manifest: dict):
    """
    纯本地逻辑：把远程清单和本地文件对比。
    返回 (changes, removed)
      changes: [{"path","kind"}...]   kind: new / changed
      removed: [{"path","skipped","reason"}...]  远程已下架；skipped=True 表示本地改过，不删
    """
    files = manifest.get("files") or {}
    state_files = (_read_state().get("files") or {})
    changes, removed = [], []
    for path, sha in files.items():
        cur = local_sha(path)
        if cur is None:
            changes.append({"path": path, "kind": "new"})
        elif cur != sha:
            changes.append({"path": path, "kind": "changed"})

    for path, old_sha in state_files.items():
        if path in files:
            continue
        # 上次同步时装过、这次清单里没了 → 远程下架
        cur = local_sha(path)
        if cur == old_sha:  # 本地没被用户改过，可以安全删除
            removed.append({"path": path, "skipped": False, "reason": "远程已下架"})
        else:
            removed.append({"path": path, "skipped": True, "reason": "远程已下架，但本地内容被修改过，保留"})
    return changes, removed


def check_update(verbose=False):
    """联网检查更新。返回给调用方（CLI/网页）的 dict。"""
    try:
        owner, repo, branch, sources, src = _resolve_remote()
        remote = {"owner": owner, "repo": repo, "branch": branch,
                  "url": f"https://github.com/{owner}/{repo}", "source": src}
    except SyncError as e:
        return {"ok": False, "configured": False, "error": str(e), "remote": None,
                "has_updates": False, "summary": "未配置远程仓库"}

    try:
        if verbose:
            print(f"  远程仓库: {remote['url']}  (分支 {branch}, 来源: {src})")
            print(f"  正在从 {', '.join(sources)} 下载清单 …")
        manifest = fetch_manifest((owner, repo, branch, sources, src))
    except SyncError as e:
        return {"ok": False, "configured": True, "error": str(e), "remote": remote,
                "has_updates": False, "summary": "检查失败"}

    changes, removed = build_plan(manifest)
    real_removed = [r for r in removed if not r["skipped"]]
    n_new = sum(1 for c in changes if c["kind"] == "new")
    n_changed = sum(1 for c in changes if c["kind"] == "changed")
    unchanged = len(manifest["files"]) - len(changes)
    has_updates = bool(changes) or bool(real_removed)
    summary = (f"远程 {len(manifest['files'])} 个文件：新增 {n_new}、更新 {n_changed}、"
               f"下架 {len(real_removed)}、未变 {unchanged}")
    if verbose:
        print("  " + summary)
    return {
        "ok": True, "configured": True, "error": None, "remote": remote,
        "manifest": {"generated_at": manifest.get("generated_at", ""), "files_count": len(manifest["files"])},
        "has_updates": has_updates,
        "status": "updates" if has_updates else "up_to_date",
        "summary": summary,
        "changes": changes, "removed": removed,
    }


# ---------------------------------------------------------------- 应用更新 ----------------------------------------------------------------

def _backup_files(rel_list):
    """把将变更/删除的文件旧版本复制到 backups/sync_backup_<时间戳>/，返回备份目录名"""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(BACKUPS_DIR, f"sync_backup_{stamp}")
    os.makedirs(folder, exist_ok=True)
    for rel in rel_list:
        src = os.path.join(BASE_DIR, rel.replace("/", os.sep))
        if os.path.isfile(src):
            dest = os.path.join(folder, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
    return os.path.relpath(folder, BASE_DIR)


def _prune_backups(keep=MAX_BACKUPS):
    try:
        names = sorted(n for n in os.listdir(BACKUPS_DIR)
                       if n.startswith("sync_backup_") and os.path.isdir(os.path.join(BACKUPS_DIR, n)))
        for old in names[:-keep]:
            shutil.rmtree(os.path.join(BACKUPS_DIR, old), ignore_errors=True)
    except OSError:
        pass


def _download_verified(owner, repo, branch, sources, rel, expect_sha):
    urls = _source_urls(owner, repo, branch, sources, rel)
    raw, _used = _http_get(urls)
    got = _sha256_bytes(raw)
    if got != expect_sha:
        raise SyncError(f"{rel} 下载后校验不一致（可能远程正在更新，请稍后重试）")
    return raw


def apply_update(verbose=False):
    """
    联网下载并应用题库更新。
    流程：下载清单 → 对比 → 全部文件先下载并校验 sha256 → 备份旧文件 → 原子写盘 → 删下架 → 记状态。
    返回 dict（ok/error/summary/...）。
    """
    with _apply_lock:
        return _apply_update_locked(verbose=verbose)


def _apply_update_locked(verbose=False):
    try:
        owner, repo, branch, sources, src = _resolve_remote()
        remote = {"owner": owner, "repo": repo, "branch": branch,
                  "url": f"https://github.com/{owner}/{repo}", "source": src}
    except SyncError as e:
        return {"ok": False, "configured": False, "error": str(e), "remote": None}

    try:
        if verbose:
            print(f"  远程仓库: {remote['url']}  (分支 {branch})")
            print(f"  正在下载清单 …")
        manifest = fetch_manifest((owner, repo, branch, sources, src))
        changes, removed = build_plan(manifest)
        to_change = [(c["path"], manifest["files"][c["path"]]) for c in changes]
        to_remove = [r for r in removed if not r["skipped"]]
    except SyncError as e:
        return {"ok": False, "configured": True, "error": str(e), "remote": remote}

    if not to_change and not to_remove:
        if verbose:
            print("  题库已经是最新的，无需更新。")
        return {"ok": True, "configured": True, "remote": remote, "applied": [], "removed": [],
                "backup": None, "summary": "题库已经是最新", "has_updates": False}

    # 1) 先全部下载并校验（任何一个失败都不动本地）
    if verbose:
        print(f"  需要下载 {len(to_change)} 个文件，正在下载并校验 …")
    downloads = {}
    for rel, sha in to_change:
        try:
            downloads[rel] = _download_verified(owner, repo, branch, sources, rel, sha)
        except SyncError as e:
            return {"ok": False, "configured": True, "error": f"{e}（本次未修改任何本地文件）",
                    "remote": remote}

    # 2) 备份旧版本
    backup = _backup_files([c["path"] for c in changes] + [r["path"] for r in to_remove])
    if verbose:
        print(f"  旧文件已备份到 {backup}/")

    # 3) 写盘（原子替换）
    applied = []
    for rel, raw in downloads.items():
        dest = os.path.join(BASE_DIR, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".sync_tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, dest)
        applied.append(rel)

    # 4) 删除远程已下架、本地又没改过的文件
    removed_ok = []
    for item in to_remove:
        dest = os.path.join(BASE_DIR, item["path"].replace("/", os.sep))
        try:
            if os.path.isfile(dest):
                os.remove(dest)
            removed_ok.append(item["path"])
        except OSError:
            pass

    # 5) 记录同步状态
    _write_state(manifest)
    _prune_backups()

    summary = (f"更新完成：下载 {len(applied)} 个、下架 {len(removed_ok)} 个"
               + (f"，跳过 {len(removed) - len(removed_ok)} 个本地改动过的下架文件" if removed_ok or removed else ""))
    if verbose:
        for p in applied:
            print(f"  ✓ {p}")
        for p in removed_ok:
            print(f"  🗑 {p}（远程已下架）")
        print("  " + summary)
    return {"ok": True, "configured": True, "remote": remote, "applied": applied,
            "removed": removed_ok, "skipped": [r["path"] for r in removed if r["skipped"]],
            "backup": backup, "summary": summary, "has_updates": False}


# ---------------------------------------------------------------- 命令行 ----------------------------------------------------------------

def _print_banner():
    print("=" * 56)
    print("          题库远程同步（GitHub）")
    print("=" * 56)


def cmd_info(argv):
    _print_banner()
    try:
        owner, repo, branch, sources, src = _resolve_remote()
        print(f"  远程仓库 : https://github.com/{owner}/{repo}")
        print(f"  分支     : {branch}")
        print(f"  配置来源 : {src}")
        print(f"  下载源   : {', '.join(sources)}")
    except SyncError as e:
        print(f"  ⚠️ {e}")
    return 0


def cmd_setup(argv):
    if len(argv) < 2:
        print("用法: python sync_bank.py setup <GitHub用户名> <仓库名> [分支名]")
        print("示例: python sync_bank.py setup zhangsan shuati main")
        return 1
    owner = argv[0].strip().lstrip("@")
    repo = argv[1].strip()
    branch = argv[2].strip() if len(argv) > 2 else "main"
    if not re.match(r"^[\w.-]+$", owner) or not re.match(r"^[\w.-]+$", repo):
        print("  ✗ 用户名/仓库名不合法（只能包含字母、数字、-、_、.）")
        return 1
    _write_json(REMOTE_CONFIG_FILE, {
        "owner": owner, "repo": repo, "branch": branch,
        "sources": [s["name"] for s in SOURCE_DEFS],
    })
    print(f"  ✓ 已写入 {os.path.basename(REMOTE_CONFIG_FILE)}")
    print(f"    远程仓库: https://github.com/{owner}/{repo}  (分支 {branch})")
    print(f"    提示：仓库必须已经存在并且是 public（除非你设置了 GITHUB_TOKEN）。")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.split("命令行用法")[0])
        print("用法:")
        print("  python sync_bank.py info")
        print("  python sync_bank.py check")
        print("  python sync_bank.py update")
        print("  python sync_bank.py setup <owner> <repo> [branch]")
        print("  python sync_bank.py build-manifest")
        return 0

    cmd, rest = argv[0], argv[1:]
    if cmd in ("check", "--check"):
        _print_banner()
        r = check_update(verbose=True)
        if not r["ok"]:
            print(f"  ✗ {r.get('error')}")
            return 1
        if r["has_updates"]:
            print("  → 有可用更新，运行  python sync_bank.py update  下载。")
        return 0

    if cmd in ("update", "--update"):
        _print_banner()
        r = apply_update(verbose=True)
        if not r["ok"]:
            print(f"  ✗ {r.get('error')}")
            return 1
        return 0

    if cmd == "info":
        return cmd_info(rest)

    if cmd == "setup":
        return cmd_setup(rest)

    if cmd == "build-manifest":
        _print_banner()
        build_manifest(verbose=True)
        return 0

    print(f"未知命令: {cmd}（运行 python sync_bank.py --help 查看用法）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
