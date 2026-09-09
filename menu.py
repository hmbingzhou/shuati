"""
主菜单逻辑模块
"""

from utils.helpers import (
    get_grade_list,
    get_subjects_by_grade,
    get_subject_list,
    yellow,
    red,
)
from brush import (
    start_brushing,
    start_brushing_all,
    start_brushing_by_type,
    start_brushing_all_by_type,
    resume_brushing,
)
from importer import import_questions
from batch_import import run_import_screen
from editor import (
    edit_question_menu,
    _edit_question,
    _remove_wrong_records_for_question,
    _get_question_preview,
)
from reporter import generate_report
from sync_bank import check_update, apply_update
from question_manager import (
    search_questions,
    load_questions,
    save_questions,
    clear_all_wrong_records,
    has_brush_progress,
    get_question_counts,
)


# 终端版暂时禁用的功能编号（对应代码保留，只是不可选择）：
# 目前仅保留「1 开始刷题」与「6 继续答题」；2 批量导入/3 编辑/4 查询/5 清空错题本 暂禁用。
TERMINAL_DISABLED = {"2", "3", "4", "5"}


def grade_selection() -> str:
    """年级选择界面，返回选择的年级名称（None 表示返回上级菜单）"""
    grades = get_grade_list()
    print("\n请选择年级：")
    for i, grade in enumerate(grades, 1):
        subs = get_subjects_by_grade(grade)
        if subs:
            print(f"  {i}. {grade}（{len(subs)}门科目）")
        else:
            print(f"  {i}. {red(f'{grade}（暂无科目）')}")
    print(f"  {len(grades) + 1}. 不限年级（全部科目混合）")
    print("  0. 返回主菜单")

    choice = input("\n请输入编号: ").strip()
    if choice == "0" or choice.lower() == "exit":
        return None

    try:
        idx = int(choice)
    except ValueError:
        print("  无效选择，请重新输入。")
        return grade_selection()

    if 1 <= idx <= len(grades):
        return grades[idx - 1]
    if idx == len(grades) + 1:
        return "不限年级"

    print("  无效选择，请重新输入。")
    return grade_selection()


def subject_selection(grade: str = None) -> str:
    """科目选择界面，返回选择的科目名称（None 表示返回上级菜单）

    Args:
        grade: 年级名称；None 表示列出全部科目（导入题目等场景）
    """
    if grade is None or grade == "不限年级":
        subjects = get_subject_list()
        title = "不限年级" if grade == "不限年级" else "全部科目"
        all_label = "所有科目（全部科目混合）"
    else:
        subjects = get_subjects_by_grade(grade)
        title = grade
        all_label = "所有科目（本年级混合）"

    if not subjects:
        print(f"  {red(f'⚠️【{title}】暂无科目，请选择其他年级。')}")
        return None

    counts = get_question_counts(subjects)

    print(f"\n请选择科目 - 【{title}】：")
    for i, subj in enumerate(subjects, 1):
        cnt = counts.get(subj, 0)
        if cnt > 0:
            print(f"  {i}. {subj}（{cnt}题）")
        else:
            print(f"  {i}. {red(f'{subj}（暂无题目）')}")

    scope_total = sum(counts.values())
    if scope_total > 0:
        print(f"  {len(subjects) + 1}. {all_label}")
    else:
        print(f"  {len(subjects) + 1}. {red(f'{all_label}（暂无题目）')}")
    print("  0. 返回上级")

    choice = input("\n请输入编号: ").strip()
    if choice == "0" or choice.lower() == "exit":
        return None

    try:
        idx = int(choice)
    except ValueError:
        print("  无效选择，请重新输入。")
        return subject_selection(grade)

    if 1 <= idx <= len(subjects):
        return subjects[idx - 1]
    if idx == len(subjects) + 1:
        return "所有科目"

    print("  无效选择，请重新输入。")
    return subject_selection(grade)


def brushing_mode_selection(grade: str, subject: str):
    """刷题模式选择

    Args:
        grade: 所选年级（用于"所有科目"混合刷题时的科目范围）
        subject: 所选科目（或"所有科目"）
    """
    print(f"\n选择刷题模式 - 【{subject}】")
    print("  1. 刷所有题")
    print("  2. 刷错题（仅从错题本中抽取该科错题）")
    print("  3. 刷填空题")
    print("  4. 刷选择题")
    print("  5. 刷判断题")
    print("  0. 返回上级菜单")

    choice = input("\n请输入编号: ").strip()
    if choice == "0" or choice.lower() == "exit":
        return

    # "所有科目"混合刷题时的科目范围
    if grade == "不限年级":
        scope = get_subject_list()
    else:
        scope = get_subjects_by_grade(grade)

    if choice == "1":
        if subject == "所有科目":
            start_brushing_all(only_wrong=False, subjects=scope)
        else:
            start_brushing(subject, only_wrong=False)
    elif choice == "2":
        if subject == "所有科目":
            start_brushing_all(only_wrong=True, subjects=scope)
        else:
            start_brushing(subject, only_wrong=True)
    elif choice == "3":
        if subject == "所有科目":
            start_brushing_all_by_type("填空题", only_wrong=False, subjects=scope)
        else:
            start_brushing_by_type(subject, "填空题", only_wrong=False)
    elif choice == "4":
        if subject == "所有科目":
            start_brushing_all_by_type("选择题", only_wrong=False, subjects=scope)
        else:
            start_brushing_by_type(subject, "选择题", only_wrong=False)
    elif choice == "5":
        if subject == "所有科目":
            start_brushing_all_by_type("判断题", only_wrong=False, subjects=scope)
        else:
            start_brushing_by_type(subject, "判断题", only_wrong=False)
    else:
        print("  无效选择，请重新输入。")
        brushing_mode_selection(grade, subject)


def start_brushing_menu():
    """开始刷题菜单：先选年级，再选科目，再选刷题模式"""
    while True:
        grade = grade_selection()
        if grade is None:
            return
        subject = subject_selection(grade)
        if subject is None:
            # 返回上级 -> 重新选择年级
            continue
        brushing_mode_selection(grade, subject)
        return


def import_menu():
    """（保留旧接口：逐题手工录入）"""
    subject = subject_selection()
    if subject is None:
        return
    if subject == "所有科目":
        print('  导入题目不支持"所有科目"，请选择具体科目。')
        return
    import_questions(subject)


def start_batch_import_menu():
    """批量导入题目菜单：先选年级，再选科目，再进入 judge 转换界面"""
    while True:
        grade = grade_selection()
        if grade is None:
            return
        subject = subject_selection(grade)
        if subject is None:
            continue  # 返回上级 -> 重新选择年级
        if subject == "所有科目":
            print('  批量导入不支持"所有科目"，请选择具体科目。')
            continue
        run_import_screen(grade, subject)
        return


def search_menu():
    """查询题目菜单"""
    keyword = input("\n请输入关键词搜索: ").strip()
    if not keyword or keyword.lower() == "exit":
        return

    results = search_questions(keyword)
    if not results:
        print(f"\n  ⚠️ 未找到包含「{keyword}」的题目。")
        return

    print(f"\n" + "=" * 50)
    print(f"           查询结果（共 {len(results)} 条）")
    print(f"           关键词：{keyword}")
    print("=" * 50)

    for idx, subj, q in results:
        preview = _get_question_preview(q)
        print(f"  {idx:>3}. [{subj}] [{q.get_type_label()}] {preview}")

    print(f"\n  0. 返回主菜单")

    try:
        choice = input("\n请输入编号查看/编辑题目: ").strip()
        if choice == "0" or choice.lower() == "exit":
            return

        idx = int(choice)
    except ValueError:
        print("  无效输入，请输入编号。")
        return

    # 查找对应题目
    target = None
    for item in results:
        if item[0] == idx:
            target = item
            break

    if target is None:
        print(f"  无效编号 {idx}")
        return

    _, subject, question = target
    print(f"\n  已选择: [{subject}] [{question.get_type_label()}]")
    print(f"  题目: {_get_question_preview(question, 60)}")
    print()
    print("  1. 修改题目")
    print("  2. 删除题目")
    print("  0. 返回")

    action = input("\n请选择操作: ").strip()

    if action == "1":
        new_q = _edit_question(subject, question)
        questions = load_questions(subject)
        for i, q in enumerate(questions):
            if q.text == question.text and q.answer == question.answer:
                questions[i] = new_q
                break
        save_questions(subject, questions)
        print(f"  ✓ 题目已更新")

    elif action == "2":
        confirm = input(f"  确认删除该题？(y/n): ").strip().lower()
        if confirm in ("y", "yes", "是"):
            questions = load_questions(subject)
            questions = [q for q in questions if q.text != question.text]
            save_questions(subject, questions)
            _remove_wrong_records_for_question(subject, question.text)
            print(f"  ✓ 题目已删除，错题本中相关记录已清理")
        else:
            print("  取消删除")

    else:
        print("  取消操作")


def update_bank_menu():
    """远程更新题库：检查 → 确认 → 下载（自动备份）"""
    print("\n" + "-" * 50)
    print("  远程更新题库（GitHub）")
    print("-" * 50)
    try:
        r = check_update()
    except Exception as e:
        print(f"  ✗ 检查失败: {e}")
        input("  按回车返回主菜单…")
        return
    if not r.get("ok"):
        print(f"  ✗ {r.get('error', '检查失败')}")
        input("  按回车返回主菜单…")
        return
    print(f"  远程仓库: {r['remote']['url']}（分支 {r['remote']['branch']}）")
    if not r.get("has_updates"):
        print(f"  {r['summary']}，无需更新。")
        input("  按回车返回主菜单…")
        return
    print(f"  {r['summary']}")
    for c in r.get("changes", []):
        kind = "新增" if c["kind"] == "new" else "更新"
        print(f"    · [{kind}] {c['path']}")
    for item in r.get("removed", []):
        tag = "跳过(本地改过)" if item["skipped"] else "下架"
        print(f"    · [{tag}] {item['path']}")
    ans = input("\n  确认下载并更新？(y/n): ").strip().lower()
    if ans not in ("y", "yes", "是"):
        print("  已取消")
        return
    try:
        res = apply_update()
    except Exception as e:
        print(f"  ✗ 更新失败: {e}")
        input("  按回车返回主菜单…")
        return
    if not res.get("ok"):
        print(f"  ✗ {res.get('error', '更新失败')}")
    else:
        print(f"  {res['summary']}")
        if res.get("backup"):
            print(f"  旧文件已备份到 backups/{res['backup']}")
    input("  按回车返回主菜单…")


def show_main_menu():
    """显示主菜单"""
    print("\n" + "=" * 50)
    print("           刷题软件 - 主菜单")
    print("=" * 50)
    print("  1. 开始刷题")
    print("  2. 批量导入题目（judge 转换）　（暂禁用）")
    print("  3. 编辑题目　（暂禁用）")
    print("  4. 查询题目　（暂禁用）")
    print("  5. 清空错题本　（暂禁用）")
    if has_brush_progress():
        print("  6. 继续答题")
    else:
        print(red("  6. 继续答题（当前无进度）"))
    print("  7. 更新题库（从远程 GitHub 同步）")
    print("  0. 退出程序")
    print("=" * 50)


def main_loop():
    """主菜单循环"""
    from reporter import init_session

    init_session()

    while True:
        show_main_menu()
        choice = input("请输入编号: ").strip()

        if choice == "1":
            start_brushing_menu()
        elif choice in TERMINAL_DISABLED:
            print(yellow(f"  ⚠️ 功能 {choice} 已暂时禁用（当前仅开放刷题与继续答题），代码保留，敬请期待。"))
        elif choice == "2":
            start_batch_import_menu()
        elif choice == "3":
            edit_question_menu()
        elif choice == "4":
            search_menu()
        elif choice == "5":
            confirm = input("  确认清空整个错题本？此操作不可恢复！(y/n): ").strip().lower()
            if confirm in ("y", "yes", "是"):
                clear_all_wrong_records()
            else:
                print("  已取消")
        elif choice == "6":
            if has_brush_progress():
                resume_brushing()
            else:
                print(yellow("⚠️ 当前没有可继续的刷题进度，请先开始刷题！"))
        elif choice == "7":
            update_bank_menu()
        elif choice == "0" or choice.lower() == "exit":
            print("\n  正在生成刷题报告...")
            report_path = generate_report()
            print(f"  刷题报告已保存至: {report_path}")
            print("  感谢使用，再见！")
            break
        else:
            print("  无效选择，请输入 0-7。")
