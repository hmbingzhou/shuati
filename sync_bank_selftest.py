# -*- coding: utf-8 -*-
"""离线自检：不联网，用猴子补丁模拟远程仓库，验证 sync_bank 全流程。"""
import json
import os
import shutil
import tempfile

import sync_bank

T = os.path.join(os.path.dirname(os.path.abspath(sync_bank.__file__)), ".sync_test_tmp")
shutil.rmtree(T, ignore_errors=True)
os.makedirs(T)
remote = os.path.join(T, "remote")
os.makedirs(os.path.join(remote, "data"))
os.makedirs(os.path.join(remote, "pictures"))

sha = sync_bank._sha256_bytes

# ---- 本地沙箱：一份旧题库 + 个人数据 + 一份“将下架”文件 ----
sync_bank.BASE_DIR = T
sync_bank.DATA_DIR = os.path.join(T, "data")
sync_bank.PICTURES_DIR = os.path.join(T, "pictures")
sync_bank.BACKUPS_DIR = os.path.join(T, "backups")
sync_bank.STATE_FILE = os.path.join(T, ".bank_sync_state.json")
os.makedirs(sync_bank.DATA_DIR)
os.makedirs(sync_bank.PICTURES_DIR)

def w(rel, content):
    p = os.path.join(T, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb" if isinstance(content, bytes) else "w", encoding=None if isinstance(content, bytes) else "utf-8") as f:
        f.write(content)

w("data/Python.json", "OLD PYTHON v1")
w("data/removed科目.json", "REMOVED OLD")
w("data/records.json", '{"me":"个人记录，绝不能动"}')
w("pictures/1.png", b"\x89PNG-OLD")

# 远程（维护者新版本）：Python 更新、新增科目、下架 removed科目、图片不变
rem_files = {
    "data/Python.json": sha(b"NEW PYTHON v2"),
    "data/新科目.json": sha("NEW SUBJECT v1".encode("utf-8")),
    "pictures/1.png": sha(b"\x89PNG-OLD"),
}
rem_manifest = {"format": 1, "generated_at": "2026-09-07", "files": rem_files}
with open(os.path.join(remote, "data_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(rem_manifest, f, ensure_ascii=False, indent=2)
# 远程实际文件内容
with open(os.path.join(remote, "data/Python.json"), "w", encoding="utf-8") as f:
    f.write("NEW PYTHON v2")
with open(os.path.join(remote, "data/新科目.json"), "w", encoding="utf-8") as f:
    f.write("NEW SUBJECT v1")
with open(os.path.join(remote, "pictures/1.png"), "wb") as f:
    f.write(b"\x89PNG-OLD")

# 本地状态：上次同步过 Python(旧) / removed科目 / 图片 —— 用于下架检测
sync_bank._write_state({"files": {
    "data/Python.json": sha(b"OLD PYTHON v1"),
    "data/removed科目.json": sha("REMOVED OLD".encode("utf-8")),
    "pictures/1.png": sha(b"\x89PNG-OLD"),
}})

# ---- 猴子补丁：模拟网络获取 ----
def fake_fetch_manifest(_ignored=None):
    # real signature: fetch_manifest(remote=(owner,repo,branch,sources,src) | None)
    with open(os.path.join(remote, "data_manifest.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def fake_download(owner, repo, branch, sources, rel, expect_sha):
    with open(os.path.join(remote, rel.replace("/", os.sep)), "rb") as f:
        raw = f.read()
    assert sync_bank._sha256_bytes(raw) == expect_sha
    return raw

sync_bank.fetch_manifest = fake_fetch_manifest
sync_bank._download_verified = fake_download

# 给沙箱配一个假远程（fetch 已被补丁接管，不会真的联网）
sync_bank.REMOTE_CONFIG_FILE = os.path.join(T, "bank_remote.json")
sync_bank._write_json(sync_bank.REMOTE_CONFIG_FILE,
                      {"owner": "octocat", "repo": "shuati", "branch": "main", "sources": ["github"]})

# ---- 断言 1：计划 ----
ch, rm = sync_bank.build_plan(rem_manifest)
kinds = {c["path"]: c["kind"] for c in ch}
assert kinds.get("data/Python.json") == "changed", ch
assert kinds.get("data/新科目.json") == "new", ch
assert "pictures/1.png" not in kinds
assert any(r["path"] == "data/removed科目.json" and not r["skipped"] for r in rm), rm
print("[ok] build_plan 识别 更新/新增/下架")

# ---- 断言 2：应用更新 ----
res = sync_bank.apply_update(verbose=True)
assert res["ok"], res
assert "data/Python.json" in res["applied"], res
assert "data/新科目.json" in res["applied"], res
assert "data/removed科目.json" in res["removed"], res

assert open(os.path.join(T, "data/Python.json"), encoding="utf-8").read() == "NEW PYTHON v2"
assert os.path.exists(os.path.join(T, "data/新科目.json"))
assert not os.path.exists(os.path.join(T, "data/removed科目.json"))
assert "记录" in open(os.path.join(T, "data/records.json"), encoding="utf-8").read(), "个人数据被动了！"
state = sync_bank._read_state()
assert state.get("files") == rem_files, state
print("[ok] 应用更新：写盘/删下架/个人数据未动/状态已记录")

# ---- 断言 3：备份里能找到旧版本 ----
backup = res["backup"]
old = os.path.join(T, backup.replace("/", os.sep), "data", "Python.json")
assert os.path.isfile(old) and open(old, encoding="utf-8").read() == "OLD PYTHON v1", old
print(f"[ok] 旧文件已备份: {res['backup']}")

# ---- 断言 4：再跑一次 = 已最新 ----
res2 = sync_bank.apply_update()
assert res2["ok"] and not res2["has_updates"] and res2["applied"] == [], res2
print("[ok] 二次更新为‘已最新’")

# ---- 断言 5：远程地址解析（纯函数） ----
assert sync_bank._parse_github_url("https://github.com/octocat/Hello-World.git") == ("octocat", "Hello-World")
assert sync_bank._parse_github_url("git@github.com:octocat/Hello-World.git") == ("octocat", "Hello-World")
assert sync_bank._parse_github_url("ssh://git@github.com/octocat/repo") == ("octocat", "repo")
assert sync_bank._parse_github_url("") is None
print("[ok] GitHub 地址解析")

# ---- 断言 6：bank_remote.json 配置读取 ----
cfg = os.path.join(T, "bank_remote.json")
sync_bank.REMOTE_CONFIG_FILE = cfg
sync_bank._write_json(cfg, {"owner": "octocat", "repo": "shuati", "branch": "dev", "sources": ["github"]})
o, r, b, s, src = sync_bank._resolve_remote()
assert (o, r, b) == ("octocat", "shuati", "dev") and src == "bank_remote.json" and s == ["github"]
print("[ok] bank_remote.json 配置识别")

shutil.rmtree(T, ignore_errors=True)
print("\n全部离线自检通过 ✔")
