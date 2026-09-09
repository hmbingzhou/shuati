"""
统计与报告生成模块
"""

import datetime
import os
from typing import Dict, List, Tuple
from utils.helpers import ensure_data_dir

# 会话数据存储（全局累计，程序运行期间持续）
session_data: Dict[str, dict] = {}
session_start_time: str = ""


class SessionStats:
    """会话统计数据"""

    def __init__(self):
        self.total = 0
        self.correct = 0
        self.wrong = 0


def init_session():
    """初始化新会话"""
    global session_data, session_start_time
    session_data = {}
    session_start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_result(subject: str, is_correct: bool):
    """记录一道题的结果"""
    global session_data
    if subject not in session_data:
        session_data[subject] = SessionStats()
    stats = session_data[subject]
    stats.total += 1
    if is_correct:
        stats.correct += 1
    else:
        stats.wrong += 1


def get_session_stats() -> Dict[str, SessionStats]:
    """获取当前会话统计数据"""
    return session_data


def generate_report() -> str:
    """生成刷题报告，返回生成的 TXT 文件路径"""
    ensure_data_dir()

    end_time = datetime.datetime.now()
    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
    report_filename = f"刷题报告_{end_time.strftime('%Y%m%d_%H%M%S')}.txt"
    report_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, report_filename)

    lines = []
    lines.append("=== 刷题统计报告 ===")
    lines.append(f"开始时间：{session_start_time}")
    lines.append(f"结束时间：{end_time_str}")

    if session_start_time:
        try:
            start_dt = datetime.datetime.strptime(
                session_start_time, "%Y-%m-%d %H:%M:%S"
            )
            delta = end_time - start_dt
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            if delta.days > 0:
                hours += delta.days * 24
            lines.append(f"总耗时：{hours}小时{minutes}分钟")
        except ValueError:
            lines.append("总耗时：未知")

    lines.append("")

    grand_total = 0
    grand_correct = 0
    grand_wrong = 0

    for subject in sorted(session_data.keys()):
        stats = session_data[subject]
        grand_total += stats.total
        grand_correct += stats.correct
        grand_wrong += stats.wrong

        lines.append(f"【{subject}】")
        lines.append(f"刷题总数：{stats.total}")
        lines.append(f"正确数：{stats.correct}")
        lines.append(f"错误数：{stats.wrong}")
        lines.append("")

    lines.append("【总计】")
    lines.append(f"刷题总数：{grand_total}")
    lines.append(f"正确数：{grand_correct}")
    lines.append(f"错误数：{grand_wrong}")
    if grand_total > 0:
        accuracy = (grand_correct / grand_total) * 100
        lines.append(f"正确率：{accuracy:.1f}%")
    else:
        lines.append("正确率：0.0%")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return report_path
