# -*- coding: utf-8 -*-
"""
服务端冒烟自检（默认模式 + SHUATI_HOME 隔离模式）
==================================================
- 默认模式：目录仍在项目根，API/静态图片正常（验证桌面零回归）。
- 隔离模式：SHUATI_HOME=临时目录，新增题目与上传图片都落到 HOME，项目 data/pictures 不被污染
  （等价模拟 Android 私有目录形态）。

用法：python server_smoke_selftest.py
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(ROOT, ".server_smoke_tmp")

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(method, url, body=None, raw=None, ctype=None, timeout=10):
    data = None
    headers = {}
    if raw is not None:
        data = raw
        headers["Content-Type"] = ctype or "application/octet-stream"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def start_server(port, home=None):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if home:
        env["SHUATI_HOME"] = home
    else:
        env.pop("SHUATI_HOME", None)
    log = open(os.path.join(TMP, f"server_{port}.log"), "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-X", "utf8", "webui_server.py",
                             "--port", str(port), "--no-browser"],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError(f"服务提前退出，见 {log.name}")
        try:
            http("GET", base + "/api/progress", timeout=2)
            return proc, base, log
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("服务启动超时")


def stop(proc, log):
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    log.close()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP)

    # ---------- 1) 默认模式：桌面零回归 ----------
    port = free_port()
    proc, base, log = start_server(port)
    try:
        ov = http("GET", base + "/api/overview")
        subs = [s for g in ov.get("grades", []) for s in g.get("subjects", [])]
        check("默认模式 /api/overview 正常", isinstance(subs, list) and len(subs) > 0, ov)

        q = http("GET", base + "/api/questions?subject=%E6%95%B0%E6%8D%AE%E7%BB%93%E6%9E%84&pageSize=1")
        items = q.get("items") or []
        check("默认模式题库读取正常（数据结构）", len(items) == 1 and items[0]["type"], q.get("total"))

        # 静态图片（取一张真实存在的科目图）
        pic_dir = os.path.join(ROOT, "pictures", "数据结构")
        names = [n for n in os.listdir(pic_dir) if n.lower().endswith(".png")]
        if names:
            with urllib.request.urlopen(f"{base}/pictures/%E6%95%B0%E6%8D%AE%E7%BB%93%E6%9E%84/{names[0]}", timeout=10) as r:
                check("默认模式静态图片 200", r.status == 200 and r.headers.get("Content-Type", "").startswith("image/"),
                      f"{r.status} {r.headers.get('Content-Type')}")
        pics = http("GET", base + "/api/pictures?dir=%E6%95%B0%E6%8D%AE%E7%BB%93%E6%9E%84")
        check("默认模式图片库按科目列出", pics["total"] == len(names), pics.get("total"))

        info = http("GET", base + "/api/bank/info")
        check("默认模式题库同步配置接口可访问", "configured" in info, info.get("error"))
    finally:
        stop(proc, log)

    # ---------- 2) 隔离模式：写入全部落 HOME ----------
    home = os.path.join(TMP, "home")
    os.makedirs(home)
    repo_java = os.path.join(ROOT, "data", "Java.json")
    before = sha(repo_java)
    port2 = free_port()
    proc2, base2, log2 = start_server(port2, home=home)
    try:
        add = http("POST", base2 + "/api/questions", {
            "subject": "Java",
            "question": {"type": "判断题", "text": "隔离模式自检题", "answer": "正确"},
        })
        check("隔离模式可新增题目", add.get("ok") is True, add)
        home_java = os.path.join(home, "data", "Java.json")
        check("题目写入 HOME/data", os.path.isfile(home_java), home_java)
        check("项目 data/Java.json 未被改写", sha(repo_java) == before)

        up = http("POST", base2 + "/api/pictures/upload?dir=Java&name=selftest_iso.png",
                  raw=b"\x89PNG\r\n\x1a\niso")
        check("隔离模式图片上传返回带目录名", up.get("ok") and up["name"] == "Java/selftest_iso.png", up)
        check("图片写入 HOME/pictures/Java",
              os.path.isfile(os.path.join(home, "pictures", "Java", "selftest_iso.png")))
        lst = http("GET", base2 + "/api/pictures?dir=Java")
        check("隔离模式图库只列 HOME 内容", lst["total"] == 1 and lst["items"][0]["name"] == "Java/selftest_iso.png", lst)

        rep = http("POST", base2 + "/api/reports", {"start_time": "2026-01-01 00:00:00",
                                                    "end_time": "2026-01-01 00:10:00",
                                                    "subjects": [{"name": "Java", "total": 1, "correct": 1, "wrong": 0}]})
        check("隔离模式报告接口可用", bool(rep.get("path")), rep)
        check("报告写入 HOME/reports", os.path.isdir(os.path.join(home, "reports"))
              and len(os.listdir(os.path.join(home, "reports"))) >= 1)
        check("项目 reports/ 未新增（隔离生效）",
              not os.path.isfile(os.path.join(ROOT, "reports", os.path.basename(rep.get("path") or "x"))))
    finally:
        stop(proc2, log2)

    shutil.rmtree(TMP, ignore_errors=True)
    print("\n" + ("服务端冒烟全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
