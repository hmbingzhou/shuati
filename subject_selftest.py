# -*- coding: utf-8 -*-
"""自检：新建科目接口（POST /api/subjects）与自定义科目持久化。

运行：python subject_selftest.py
"""
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.join(ROOT, ".probe_subject_selftest")
shutil.rmtree(HOME, ignore_errors=True)
os.environ["SHUATI_HOME"] = HOME
sys.path.insert(0, ROOT)

import webui_server as S  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        fails.append(name)


PORT = 8891
BASE = f"http://127.0.0.1:{PORT}"


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def main():
    srv = S.ThreadingHTTPServer(("127.0.0.1", PORT), S.ApiHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)
    try:
        r = http("POST", "/api/subjects", {"grade": "大二下", "name": "概率论与数理统计"})
        check("新建科目成功", r.get("ok") is True and r.get("subject") == "概率论与数理统计", r)

        ov = http("GET", "/api/overview")
        grade = next((g for g in ov["grades"] if g["name"] == "大二下"), None)
        names = [s["name"] for s in (grade or {}).get("subjects", [])]
        check("新科目出现在 overview 的大二下", "概率论与数理统计" in names, names)

        subj = next((s for s in (grade or {}).get("subjects", []) if s["name"] == "概率论与数理统计"), {})
        check("新科目题数为 0", subj.get("questionCount") == 0, subj)

        dup = http("POST", "/api/subjects", {"grade": "大二上", "name": "概率论与数理统计"})
        check("同名科目被拒绝", dup.get("ok") is False and "已存在" in str(dup.get("error")), dup)

        empty = http("POST", "/api/subjects", {"grade": "大二下", "name": "   "})
        check("空名字被拒绝", empty.get("ok") is False, empty)

        bad = http("POST", "/api/subjects", {"grade": "大五上", "name": "随便"})
        check("未知年级被拒绝", bad.get("ok") is False, bad)

        cfg = os.path.join(HOME, "data", "subjects_custom.json")
        saved = json.load(open(cfg, encoding="utf-8")) if os.path.exists(cfg) else {}
        check("写入 data/subjects_custom.json", saved.get("大二下") == ["概率论与数理统计"], saved)

        lst = http("GET", "/api/questions?" + urllib.parse.urlencode({"subject": "概率论与数理统计"}))
        check("新科目题库为空", lst.get("total") == 0, lst.get("total"))

        add = http("POST", "/api/questions", {"subject": "概率论与数理统计", "question": {
            "type": "判断题", "text": "概率的公理满足可列可加性。", "answer": "正确"}})
        check("能往新科目加题", add.get("ok") is True, add)
        lst2 = http("GET", "/api/questions?" + urllib.parse.urlencode({"subject": "概率论与数理统计"}))
        check("加题后题数为 1", lst2.get("total") == 1, lst2.get("total"))

        # 重启后仍然存在（模拟进程重启：重新读配置文件）
        from utils.helpers import get_subjects_by_grade
        check("重启后科目仍在（读配置文件）", "概率论与数理统计" in get_subjects_by_grade("大二下"),
              get_subjects_by_grade("大二下"))
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(HOME, ignore_errors=True)

    print("\n" + ("新建科目自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
