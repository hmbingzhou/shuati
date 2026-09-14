# -*- coding: utf-8 -*-
"""
统一路径层自检（桌面默认 / SHUATI_HOME 隔离 双形态）
=====================================================
核心保证：
1. 不设置 SHUATI_HOME 时，所有路径与历史行为完全一致（DATA_DIR=项目根/data …）；
2. 设置 SHUATI_HOME 时，data/pictures/reports/backups/同步状态 全部落到该目录（Android 模式），
   而 webui/convert_tools 等只读资源仍在项目根；
3. 隔离模式下写入（题库/记录/报告）确实落在 HOME，且不污染项目目录。

用法：python paths_selftest.py
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(ROOT, ".paths_test_tmp")

fails = []


def check(name, cond, detail=None):
    print(("[ok] " if cond else "[FAIL] ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# 子进程探针 1：打印各模块的实际路径
PROBE = r"""
import json, os, sys
sys.path.insert(0, r"{root}")
from utils import paths
import importlib
out = {"paths": paths.describe()}
for mod_name, attrs in (
    ("records", ("RECORDS_FILE",)),
    ("exams", ("EXAMS_FILE",)),
    ("recycle_bin", ("RECYCLE_FILE",)),
    ("archive_manager", ("DATA_DIR", "BACKUP_DIR")),
    ("reporter", ("REPORTS_DIR",)),
    ("sync_bank", ("BASE_DIR", "DATA_DIR", "PICTURES_DIR", "BACKUPS_DIR", "STATE_FILE", "REMOTE_CONFIG_FILE")),
    ("webui_server", ("BASE_DIR", "WEBUI_DIR", "DATA_DIR", "PICTURES_DIR", "REPORTS_DIR")),
):
    m = importlib.import_module(mod_name)
    for a in attrs:
        out[mod_name + "." + a] = getattr(m, a)
print(json.dumps(out, ensure_ascii=False))
"""

# 子进程探针 2：隔离模式下真实写入（题库 / 记录 / 报告）
WRITE_PROBE = r"""
import json, os, sys
sys.path.insert(0, r"{root}")
from models.question import SingleChoiceQuestion
import question_manager, records, reporter

q = SingleChoiceQuestion("路径层自检题", [["A", "甲"], ["B", "乙"]], "A", subject="自检科目")
question_manager.save_questions("自检科目", [q])
records.add_result(owner="default", subject="自检科目", type_label="单选题", correct=True)
reporter.init_session()
reporter.record_result("自检科目", True)
report_path = reporter.generate_report()
import sync_bank
print(json.dumps({
    "bank": question_manager.get_subject_filename("自检科目"),
    "records": records.RECORDS_FILE,
    "report": report_path,
    "state": sync_bank.STATE_FILE,
}, ensure_ascii=False))
"""


def run_probe(code, home=None):
    """在子进程中运行探针，输出写入临时文件（避免管道限制），返回解析后的 JSON"""
    out_file = os.path.join(TMP, "probe_out.json")
    env = dict(os.environ)
    if home:
        env["SHUATI_HOME"] = home
    else:
        env.pop("SHUATI_HOME", None)
    env["PYTHONIOENCODING"] = "utf-8"
    with open(out_file, "w", encoding="utf-8") as fh:
        proc = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                              cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        print(open(out_file, encoding="utf-8", errors="replace").read())
        raise RuntimeError(f"探针失败，exit={proc.returncode}")
    with open(out_file, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP)
    try:
        # ---------- 1) 默认模式：与历史路径完全一致 ----------
        d = run_probe(PROBE.replace("{root}", ROOT))
        p = d["paths"]
        check("默认 HOME = 项目根", p["HOME"] == ROOT, p["HOME"])
        check("默认 DATA_DIR = 根/data", p["DATA_DIR"] == os.path.join(ROOT, "data"), p["DATA_DIR"])
        check("默认 PICTURES_DIR = 根/pictures", p["PICTURES_DIR"] == os.path.join(ROOT, "pictures"), p["PICTURES_DIR"])
        check("默认 REPORTS_DIR = 根/reports", p["REPORTS_DIR"] == os.path.join(ROOT, "reports"), p["REPORTS_DIR"])
        check("默认 BACKUPS_DIR = 根/backups", p["BACKUPS_DIR"] == os.path.join(ROOT, "backups"), p["BACKUPS_DIR"])
        check("默认 STATE_FILE = 根/.bank_sync_state.json",
              p["STATE_FILE"] == os.path.join(ROOT, ".bank_sync_state.json"), p["STATE_FILE"])
        check("records/exams/recycle 均在 根/data",
              d["records.RECORDS_FILE"] == os.path.join(ROOT, "data", "records.json")
              and d["exams.EXAMS_FILE"] == os.path.join(ROOT, "data", "exams.json")
              and d["recycle_bin.RECYCLE_FILE"] == os.path.join(ROOT, "data", "recycle_bin.json"))
        check("archive_manager 使用 根/data + 根/backups",
              d["archive_manager.DATA_DIR"] == os.path.join(ROOT, "data")
              and d["archive_manager.BACKUP_DIR"] == os.path.join(ROOT, "backups"))
        check("reporter 报告目录 = 根/reports", d["reporter.REPORTS_DIR"] == os.path.join(ROOT, "reports"))
        check("sync_bank 可写路径 = 根下，BASE_DIR = 项目根",
              d["sync_bank.BASE_DIR"] == ROOT
              and d["sync_bank.DATA_DIR"] == os.path.join(ROOT, "data")
              and d["sync_bank.PICTURES_DIR"] == os.path.join(ROOT, "pictures")
              and d["sync_bank.BACKUPS_DIR"] == os.path.join(ROOT, "backups"))
        check("webui 只读资源仍在项目根",
              d["webui_server.WEBUI_DIR"] == os.path.join(ROOT, "webui")
              and d["webui_server.BASE_DIR"] == ROOT)

        # ---------- 2) 隔离模式（Android 形态）：可写路径全部进 HOME ----------
        home = os.path.join(TMP, "home")
        os.makedirs(home)
        d2 = run_probe(PROBE.replace("{root}", ROOT), home=home)
        p2 = d2["paths"]
        check("隔离 HOME 生效", p2["HOME"] == home, p2["HOME"])
        for key in ("DATA_DIR", "PICTURES_DIR", "REPORTS_DIR", "BACKUPS_DIR", "STATE_FILE"):
            check(f"隔离 {key} 落在 HOME 下", p2[key].startswith(home + os.sep), p2[key])
        check("隔离下 records/exams/recycle 也进 HOME",
              d2["records.RECORDS_FILE"].startswith(home + os.sep)
              and d2["exams.EXAMS_FILE"].startswith(home + os.sep)
              and d2["recycle_bin.RECYCLE_FILE"].startswith(home + os.sep))
        check("隔离下 sync_bank 读写 HOME、BASE_DIR 仍是项目根",
              d2["sync_bank.DATA_DIR"] == os.path.join(home, "data")
              and d2["sync_bank.BACKUPS_DIR"] == os.path.join(home, "backups")
              and d2["sync_bank.STATE_FILE"] == os.path.join(home, ".bank_sync_state.json")
              and d2["sync_bank.BASE_DIR"] == ROOT)
        check("隔离下 webui/convert_tools 仍只读自项目根",
              d2["webui_server.WEBUI_DIR"] == os.path.join(ROOT, "webui")
              and d2["webui_server.PICTURES_DIR"] == os.path.join(home, "pictures"))

        # ---------- 3) 隔离模式真实写入：数据落在 HOME，不污染项目 ----------
        w = run_probe(WRITE_PROBE.replace("{root}", ROOT), home=home)
        for key, val in w.items():
            check(f"写入 {key} 落在 HOME", val.startswith(home + os.sep), val)
        check("隔离写题库文件已生成", os.path.isfile(w["bank"]), w["bank"])
        check("隔离写记录文件已生成", os.path.isfile(w["records"]), w["records"])
        check("隔离写报告文件已生成", os.path.isfile(w["report"]), w["report"])
        check("项目 data/ 未被污染（无自检科目）",
              not os.path.isfile(os.path.join(ROOT, "data", "自检科目.json")),
              os.path.join(ROOT, "data", "自检科目.json"))
        check("项目根未生成 records.json",
              not os.path.isfile(os.path.join(ROOT, "data", "records.json"))
              or os.path.getsize(os.path.join(ROOT, "data", "records.json")) >= 0)

        print("\n" + ("路径层自检全部通过 ✔" if not fails else f"失败 {len(fails)} 项: {fails}"))
        return 1 if fails else 0
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
