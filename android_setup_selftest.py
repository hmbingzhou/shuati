# -*- coding: utf-8 -*-
"""
Android 工程验收自检（不需要 Android SDK / Gradle）
====================================================
覆盖：
1. 构建期 staging 生成与完整性（prepare_python_src.py）；
2. Gradle / Manifest / 资源配置的关键内容检查（XML 可解析、权限与 localhost 明文放行、Chaquopy 配置）；
3. 种子复制行为（首启复制、再次幂等、绝不覆盖已有文件）；
4. 真实启动：走 entry.start() 起本地服务，HTTP 校验首页/题库/manifest 均正常。

用法：python android_setup_selftest.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
ANDROID = os.path.join(ROOT, "android")
STAGING = os.path.join(ANDROID, "app", "src", "main", "python")
TMP_HOME = os.path.join(ROOT, ".seed_test_home")
TMP = os.path.join(ROOT, ".android_test_tmp")

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def load_prepare():
    spec = importlib.util.spec_from_file_location(
        "prepare_python_src", os.path.join(ANDROID, "prepare_python_src.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROBE = r"""
import json, os, sys, urllib.parse, urllib.request
staging, home = sys.argv[1], sys.argv[2]
sys.path.insert(0, staging)
import entry

first = entry.ensure_home(home)
data_dir = os.path.join(home, "data")
bank = sorted(f for f in os.listdir(data_dir) if f.endswith(".json"))[0]
bank_path = os.path.join(data_dir, bank)
with open(bank_path, "w", encoding="utf-8") as f:
    f.write('[{"type": "判断题", "text": "自定义内容", "answer": "正确"}]')
os.remove(os.path.join(home, ".seed_version"))      # 强制再次执行种子流程
second = entry.ensure_home(home)
with open(bank_path, encoding="utf-8") as f:
    custom_kept = "自定义内容" in f.read()

port = entry.start(home)

def get(path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=15) as r:
        return r.status, r.read().decode("utf-8")

_, html = get("/")
_, qj = get("/api/questions?subject=" + urllib.parse.quote("数据结构") + "&pageSize=1")
_, mf = get("/manifest.webmanifest")
print(json.dumps({
    "first_copied": first["copied"],
    "second_copied": second["copied"],
    "custom_kept": custom_kept,
    "port": port,
    "index_nav": 'id="bottom-nav"' in html,
    "seed_questions": len((json.loads(qj).get("items") or [])),
    "manifest_ok": json.loads(mf).get("display") == "standalone",
}, ensure_ascii=False))
"""


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    shutil.rmtree(TMP_HOME, ignore_errors=True)
    os.makedirs(TMP)
    try:
        # ---------- 1) staging 生成 ----------
        prep = load_prepare()
        prep.build(clean=True)
        check("staging 校验通过", prep.check() == 0)
        for rel in ("entry.py", "webui_server.py", "models/question.py", "utils/paths.py",
                    "webui/app.js", "webui/manifest.webmanifest", "convert_tools/judges.py",
                    "seed/bank_remote.json", "seed/seed_version.json"):
            check(f"staging 含 {rel}", os.path.isfile(os.path.join(STAGING, rel.replace("/", os.sep))))
        seed_banks = [f for f in os.listdir(os.path.join(STAGING, "seed", "data")) if f.endswith(".json")]
        repo_banks = [f for f in os.listdir(os.path.join(ROOT, "data"))
                      if f.endswith(".json") and f not in prep.USER_DATA_FILES]
        check("种子题库与仓库题库数量一致", sorted(seed_banks) == sorted(repo_banks),
              f"{len(seed_banks)} vs {len(repo_banks)}")
        check("种子未包含个人数据",
              not any(f in seed_banks for f in ("records.json", "wrong_book.json", "recycle_bin.json")))
        cfg = json.load(open(os.path.join(STAGING, "seed", "bank_remote.json"), encoding="utf-8"))
        check("种子含远程题库配置 owner/repo", bool(cfg.get("owner")) and bool(cfg.get("repo")), cfg)
        pics = sum(len(files) for _d, _s, files in os.walk(os.path.join(STAGING, "seed", "pictures")))
        check("种子含题目图片", pics > 0, pics)

        # ---------- 2) 工程配置检查 ----------
        ns = "{http://schemas.android.com/apk/res/android}"
        m_root = ET.parse(os.path.join(ANDROID, "app", "src", "main", "AndroidManifest.xml")).getroot()
        perms = [p.get(ns + "name") for p in m_root.findall("uses-permission")]
        app = m_root.find("application")
        check("Manifest 声明 INTERNET 权限", "android.permission.INTERNET" in perms, perms)
        check("Manifest 使用 PyApplication 且主 Activity 导出",
              app.get(ns + "name", "").endswith("PyApplication")
              and any(a.get(ns + "name", "").endswith("MainActivity")
                      and a.get(ns + "exported") == "true" for a in app.findall("activity")))
        check("Manifest 引用 networkSecurityConfig",
              app.get(ns + "networkSecurityConfig") == "@xml/network_security_config")

        nsc = ET.parse(os.path.join(ANDROID, "app", "src", "main", "res", "xml",
                                    "network_security_config.xml")).getroot()
        base = nsc.find("base-config")
        domains = {d.text for dc in nsc.findall("domain-config") for d in dc.findall("domain")}
        check("network config：默认禁明文，仅放行 localhost",
              base is not None and base.get("cleartextTrafficPermitted") == "false"
              and {"127.0.0.1", "localhost"} <= domains, domains)
        for rel in ("res/values/strings.xml", "res/values/styles.xml"):
            ET.parse(os.path.join(ANDROID, "app", "src", "main", rel.replace("/", os.sep)))
        check("资源 XML 可解析（strings/styles）", True)
        for d in ("mipmap-mdpi", "mipmap-xxxhdpi"):
            icon = os.path.join(ANDROID, "app", "src", "main", "res", d, "ic_launcher.png")
            check(f"图标存在 {d}", os.path.isfile(icon) and os.path.getsize(icon) > 0)

        app_gradle = open(os.path.join(ANDROID, "app", "build.gradle.kts"), encoding="utf-8").read()
        check("Gradle：Chaquopy 17 + Python 3.14 + arm64-v8a",
              'id("com.chaquo.python")' in app_gradle and 'version = "3.14"' in app_gradle
              and 'abiFilters += listOf("arm64-v8a")' in app_gradle
              and "minSdk = 24" in app_gradle)
        root_gradle = open(os.path.join(ANDROID, "build.gradle.kts"), encoding="utf-8").read()
        wrapper = open(os.path.join(ANDROID, "gradle", "wrapper",
                                    "gradle-wrapper.properties"), encoding="utf-8").read()
        check("Gradle：AGP 与 Gradle 版本固定（8.7.3 / 8.9）",
              "8.7.3" in root_gradle and "17.0.0" in root_gradle and "gradle-8.9-bin.zip" in wrapper)
        java = open(os.path.join(ANDROID, "app", "src", "main", "java", "com", "hmbingzhou",
                                 "shuati", "MainActivity.java"), encoding="utf-8").read()
        check("MainActivity：WebView + 文件选择 + 返回键桥接",
              "loadUrl(\"http://127.0.0.1:" in java and "onShowFileChooser" in java
              and "evaluateJavascript" in java and "__shuatiAndroidBack" in java)
        check("entry.py 可编译",
              subprocess.run([sys.executable, "-m", "py_compile",
                              os.path.join(ANDROID, "entry.py")]).returncode == 0)

        # ---------- 2b) 构建脚本可用性（PS 5.1 对编码/执行策略敏感） ----------
        ps1 = os.path.join(ANDROID, "build_apk.ps1")
        with open(ps1, "rb") as fh:
            head = fh.read(3)
        check("build_apk.ps1 带 UTF-8 BOM（PS 5.1 必需）", head == b"\xef\xbb\xbf", head)
        parse_out = os.path.join(TMP, "ps_parse.txt")
        cmd = ("$null = [scriptblock]::Create([IO.File]::ReadAllText('%s',[Text.Encoding]::UTF8)); 'PARSE_OK'"
               % ps1.replace("'", "''"))
        with open(parse_out, "w", encoding="utf-8") as fh:
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           stdout=fh, stderr=subprocess.STDOUT)
        parsed = open(parse_out, encoding="utf-8", errors="replace").read()
        check("build_apk.ps1 语法可解析", "PARSE_OK" in parsed, parsed[-300:])
        bat = os.path.join(ANDROID, "build_apk.bat")
        bat_bytes = open(bat, "rb").read() if os.path.isfile(bat) else b""
        check("build_apk.bat 存在且为纯 ASCII（cmd 兼容）",
              bool(bat_bytes) and all(b < 128 for b in bat_bytes))

        # ---------- 3) 种子行为 + 真实启动（子进程，保持模块状态干净） ----------
        out_file = os.path.join(TMP, "probe.json")
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("SHUATI_HOME", None)
        with open(out_file, "w", encoding="utf-8") as fh:
            proc = subprocess.run([sys.executable, "-X", "utf8", "-c", PROBE, STAGING, TMP_HOME],
                                  cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT)
        raw = open(out_file, encoding="utf-8", errors="replace").read()
        if proc.returncode != 0:
            print(raw)
            check("Android 启动探针执行成功", False, f"exit={proc.returncode}")
        else:
            check("Android 启动探针执行成功", True)
            res = json.loads(raw.strip().splitlines()[-1])
            check("首启种子有复制", res["first_copied"] > 0, res["first_copied"])
            check("再次执行种子复制幂等且不覆盖已有文件",
                  res["second_copied"] >= 0 and res["custom_kept"], res)
            check("entry.start 返回可用端口", isinstance(res["port"], int) and res["port"] > 0, res["port"])
            check("首页含移动端底部导航", res["index_nav"])
            check("种子题库可被服务读取（数据结构）", res["seed_questions"] == 1, res["seed_questions"])
            check("manifest 可访问且为 standalone", res["manifest_ok"])

        print("\n" + ("Android 工程自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
        return 1 if fails else 0
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
        shutil.rmtree(TMP_HOME, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
