"""
刷题界面核心逻辑模块
"""

import random
from typing import List, Optional, Dict, Any
from models.question import Question, ChoiceQuestion, TrueFalseQuestion, FillBlankQuestion
from question_manager import (
    load_questions,
    add_wrong_record,
    remove_wrong_record,
    update_wrong_record_timestamp,
    get_wrong_records_by_subject,
    save_brush_progress,
    load_brush_progress,
    clear_brush_progress,
    has_brush_progress,
)
from reporter import record_result
from utils.helpers import green, red, yellow


def _get_type_class(type_label: str):
    """
    根据题型标签返回对应的 Question 子类。
    用于 isinstance 过滤。

    题型标签映射：
        "填空题" -> FillBlankQuestion
        "选择题" -> ChoiceQuestion（包含单选+多选）
        "判断题" -> TrueFalseQuestion
    """
    _TYPE_MAP = {
        "填空题": FillBlankQuestion,
        "选择题": ChoiceQuestion,
        "判断题": TrueFalseQuestion,
    }
    return _TYPE_MAP.get(type_label)


def _filter_by_type(questions: List[Question], type_label: str) -> List[Question]:
    """按题型标签过滤题目列表"""
    q_class = _get_type_class(type_label)
    if q_class is None:
        return questions
    return [q for q in questions if isinstance(q, q_class)]


def _get_answer_prompt(question: Question) -> str:
    """根据题型生成输入提示语"""
    # 对于多选题，增加特殊提示
    if isinstance(question, ChoiceQuestion) and question.choice_type == "multiple":
        return "请输入答案（如：A C D，答案之间用空格隔开）: "
    elif question.get_type_label() == "判断题":
        return "请输入答案（正确/错误 / 对/错 / t/f / true/false）: "
    else:
        return "请输入答案: "


def _display_question(question: Question, current: int, total: int):
    """显示题目，带题号计数器"""
    print("-" * 50)
    print(f"  题目 {current}/{total}")
    print(question.display())
    print()


def _save_progress_on_exit(subject: str, remaining: List[Question], total: int,
                           mode: str, type_label: str = None):
    """退出时保存刷题进度"""
    remaining_data = [
        {"subject": q.subject, "text": q.text}
        for q in remaining
    ]
    progress = {
        "subject": subject,
        "mode": mode,
        "type_label": type_label,
        "remaining": remaining_data,
        "total": total,
    }
    save_brush_progress(progress)
    print(yellow("\n⚠️ 进度已保存，可使用「继续答题」接着刷。"))


def _rebuild_question(subject: str, text: str) -> Optional[Question]:
    """根据科目和题目文本重建 Question 对象"""
    all_questions = load_questions(subject)
    for q in all_questions:
        if q.text == text:
            return q
    return None


def resume_brushing():
    """继续上次未完成的刷题"""
    progress = load_brush_progress()
    if not progress:
        print(yellow("⚠️ 当前没有可继续的刷题进度！"))
        return

    subject = progress.get("subject", "")
    mode = progress.get("mode", "all")
    type_label = progress.get("type_label")
    remaining_data = progress.get("remaining", [])
    total = progress.get("total", 0)

    # 重建题目列表
    remaining = []
    for item in remaining_data:
        subj = item.get("subject", subject)
        text = item.get("text", "")
        q = _rebuild_question(subj, text)
        if q:
            remaining.append(q)

    if not remaining:
        print(yellow("⚠️ 进度文件中的题目均已不存在，进度已清除。"))
        clear_brush_progress()
        return

    processed = total - len(remaining)
    print(f"\n  【继续答题】- {subject} - 已答 {processed}/{total} 题，剩余 {len(remaining)} 题")
    print("  输入 exit 返回菜单\n")

    for i, question in enumerate(remaining, processed + 1):
        _display_question(question, i, total)

        prompt = _get_answer_prompt(question)
        user_answer = input(prompt).strip()
        if user_answer.lower() == "exit":
            # 保存剩余进度
            still_remaining = remaining[(i - processed - 1):]
            _save_progress_on_exit(subject, still_remaining, total, mode, type_label)
            return

        is_correct = question.check_answer(user_answer)
        if is_correct:
            print(green("\n✅回答正确！"))
            record_result(question.subject, True)
        else:
            print(red("\n❌回答错误！"))
            print(f"  正确答案：{question.answer}")
            print(f"  你的答案：{user_answer}")
            record_result(question.subject, False)
            add_wrong_record(question.subject, question, user_answer)

        print()

    # 全部答完，清除进度
    clear_brush_progress()
    print(green(f"✅ 继续答题完成！进度已清除。"))


def start_brushing(subject: str, only_wrong: bool = False):
    """
    开始刷题

    Args:
        subject: 科目名称
        only_wrong: True=刷错题, False=刷所有题
    """
    if only_wrong:
        wrong_records = get_wrong_records_by_subject(subject)
        if not wrong_records:
            print(f"{yellow(f'⚠️【{subject}】错题本为空，无需复习！')}")
            return

        total = len(wrong_records)
        # 从错题本加载题目
        print(f"\n  【{subject}】错题复习 - 共 {total} 道错题")
        print("  输入 exit 返回菜单\n")

        # 打乱错题顺序
        random.shuffle(wrong_records)

        for i, record in enumerate(wrong_records, 1):
            # 根据错题记录中的题目文本，从题库中找到对应的题目对象
            all_questions = load_questions(record.subject)
            question = None
            for q in all_questions:
                if q.text == record.question_text:
                    question = q
                    break

            if question is None:
                print(f"\n  [跳过] 题目未在题库中找到: {record.question_text[:30]}...")
                continue

            # 显示题目
            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                # 保存进度：剩余错题记录
                remaining_records = wrong_records[i-1:]
                remaining_questions = []
                for wr in remaining_records:
                    q = _rebuild_question(wr.subject, wr.question_text)
                    if q:
                        remaining_questions.append(q)
                _save_progress_on_exit(subject, remaining_questions, total, "wrong")
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(subject, True)
                # 做对：从错题本中移除
                remove_wrong_record(subject, question.text)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(subject, False)
                # 做错：先移除再重新加入（更新时间戳）
                update_wrong_record_timestamp(subject, question.text)

            print()
        clear_brush_progress()
        print(f"{green(f'✅【{subject}】错题复习完成！')}")

    else:
        # 刷所有题
        questions = load_questions(subject)
        if not questions:
            print(f"{yellow(f'⚠️【{subject}】题库为空，请先导入题目！')}")
            return

        total = len(questions)
        print(f"\n  【{subject}】刷题 - 共 {total} 道题")
        print("  输入 exit 返回菜单\n")

        # 打乱题目顺序
        random.shuffle(questions)

        for i, question in enumerate(questions, 1):
            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                remaining = questions[i-1:]
                _save_progress_on_exit(subject, remaining, total, "all")
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(subject, True)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(subject, False)
                # 记录到错题本
                add_wrong_record(subject, question, user_answer)

            print()
        clear_brush_progress()
        print(f"{green(f'✅【{subject}】刷题完成！')}")


def start_brushing_all(only_wrong: bool = False, subjects: List[str] = None):
    """所有科目混合出题

    Args:
        only_wrong: True=仅从错题本中抽取, False=刷所有题
        subjects: 科目范围；None 表示全部科目
    """
    if subjects is None:
        from utils.helpers import get_subject_list

        subjects = get_subject_list()

    if only_wrong:
        # 所有科目错题混合
        all_records = []
        for subj in subjects:
            records = get_wrong_records_by_subject(subj)
            all_records.extend(records)

        if not all_records:
            print(yellow("⚠️所有科目的错题本均为空，无需复习！"))
            return

        total = len(all_records)
        print(f"\n  【所有科目】错题复习 - 共 {total} 道错题")
        print("  输入 exit 返回菜单\n")

        random.shuffle(all_records)

        for i, record in enumerate(all_records, 1):
            all_questions = load_questions(record.subject)
            question = None
            for q in all_questions:
                if q.text == record.question_text:
                    question = q
                    break

            if question is None:
                continue

            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                remaining_records = all_records[i-1:]
                remaining_questions = []
                for wr in remaining_records:
                    q = _rebuild_question(wr.subject, wr.question_text)
                    if q:
                        remaining_questions.append(q)
                _save_progress_on_exit("所有科目", remaining_questions, total, "all_wrong")
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(record.subject, True)
                remove_wrong_record(record.subject, question.text)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(record.subject, False)
                update_wrong_record_timestamp(record.subject, question.text)

            print()

        clear_brush_progress()
        print(green("✅【所有科目】错题复习完成！"))

    else:
        # 所有科目混合刷题
        all_questions = []
        for subj in subjects:
            qs = load_questions(subj)
            all_questions.extend(qs)

        if not all_questions:
            print(yellow("\n⚠️题库为空，请先导入题目！"))
            return

        total = len(all_questions)
        print(f"\n  【所有科目】混合刷题 - 共 {total} 道题")
        print("  输入 exit 返回菜单\n")

        random.shuffle(all_questions)

        for i, question in enumerate(all_questions, 1):
            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                remaining = all_questions[i-1:]
                _save_progress_on_exit("所有科目", remaining, total, "all")
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(question.subject, True)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(question.subject, False)
                add_wrong_record(question.subject, question, user_answer)

            print()

        clear_brush_progress()
        print(green("✅【所有科目】混合刷题完成！"))


def start_brushing_by_type(subject: str, type_label: str, only_wrong: bool = False):
    """
    按题型刷题（单个科目）

    Args:
        subject: 科目名称
        type_label: 题型标签（"填空题" / "选择题" / "判断题"）
        only_wrong: True=仅从错题本中抽取该题型错题, False=刷该题型所有题
    """
    if only_wrong:
        # 从错题本中筛选指定题型的错题
        wrong_records = get_wrong_records_by_subject(subject)
        if not wrong_records:
            print(f"{yellow(f'⚠️【{subject}】错题本为空，无需复习！')}")
            return

        # 按题型过滤错题记录
        filtered_records = [r for r in wrong_records if r.question_type == type_label]
        if not filtered_records:
            print(f"{yellow(f'⚠️【{subject}】错题本中没有{type_label}！')}")
            return

        total = len(filtered_records)
        print(f"\n  【{subject}】{type_label} - 错题复习 - 共 {total} 道题")
        print("  输入 exit 返回菜单\n")

        random.shuffle(filtered_records)

        for i, record in enumerate(filtered_records, 1):
            all_questions = load_questions(record.subject)
            question = None
            for q in all_questions:
                if q.text == record.question_text:
                    question = q
                    break

            if question is None:
                print(f"\n  [跳过] 题目未在题库中找到: {record.question_text[:30]}...")
                continue

            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                remaining_records = filtered_records[i-1:]
                remaining_questions = []
                for wr in remaining_records:
                    q = _rebuild_question(wr.subject, wr.question_text)
                    if q:
                        remaining_questions.append(q)
                _save_progress_on_exit(subject, remaining_questions, total, "by_type_wrong", type_label)
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(subject, True)
                remove_wrong_record(subject, question.text)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(subject, False)
                update_wrong_record_timestamp(subject, question.text)

            print()
        clear_brush_progress()
        print(f"{green(f'✅【{subject}】{type_label}错题复习完成！')}")

    else:
        # 刷该题型所有题
        questions = load_questions(subject)
        if not questions:
            print(f"{yellow(f'⚠️【{subject}】题库为空，请先导入题目！')}")
            return

        # 按题型过滤
        filtered = _filter_by_type(questions, type_label)
        if not filtered:
            print(f"{yellow(f'⚠️【{subject}】题库中没有{type_label}！')}")
            return

        total = len(filtered)
        print(f"\n  【{subject}】{type_label} - 共 {total} 道题")
        print("  输入 exit 返回菜单\n")

        random.shuffle(filtered)

        for i, question in enumerate(filtered, 1):
            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                remaining = filtered[i-1:]
                _save_progress_on_exit(subject, remaining, total, "by_type", type_label)
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(subject, True)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(subject, False)
                add_wrong_record(subject, question, user_answer)

            print()
        clear_brush_progress()
        print(f"{green(f'✅【{subject}】{type_label}刷题完成！')}")


def start_brushing_all_by_type(type_label: str, only_wrong: bool = False,
                               subjects: List[str] = None):
    """
    所有科目按题型混合出题

    Args:
        type_label: 题型标签（"填空题" / "选择题" / "判断题"）
        only_wrong: True=仅从错题本中抽取, False=刷所有题
        subjects: 科目范围；None 表示全部科目
    """
    if subjects is None:
        from utils.helpers import get_subject_list

        subjects = get_subject_list()

    if only_wrong:
        # 所有科目错题混合，按题型过滤
        all_records = []
        for subj in subjects:
            records = get_wrong_records_by_subject(subj)
            # 按题型过滤
            filtered = [r for r in records if r.question_type == type_label]
            all_records.extend(filtered)

        if not all_records:
            print(yellow(f"⚠️所有科目的错题本中没有{type_label}！"))
            return

        total = len(all_records)
        print(f"\n  【所有科目】{type_label} - 错题复习 - 共 {total} 道题")
        print("  输入 exit 返回菜单\n")

        random.shuffle(all_records)

        for i, record in enumerate(all_records, 1):
            all_questions = load_questions(record.subject)
            question = None
            for q in all_questions:
                if q.text == record.question_text:
                    question = q
                    break

            if question is None:
                continue

            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                remaining_records = all_records[i-1:]
                remaining_questions = []
                for wr in remaining_records:
                    q = _rebuild_question(wr.subject, wr.question_text)
                    if q:
                        remaining_questions.append(q)
                _save_progress_on_exit("所有科目", remaining_questions, total, "all_by_type_wrong", type_label)
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(record.subject, True)
                remove_wrong_record(record.subject, question.text)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(record.subject, False)
                update_wrong_record_timestamp(record.subject, question.text)

            print()

        clear_brush_progress()
        print(green(f"✅【所有科目】{type_label}错题复习完成！"))

    else:
        # 所有科目混合，按题型过滤
        all_questions = []
        for subj in subjects:
            qs = load_questions(subj)
            all_questions.extend(qs)

        if not all_questions:
            print(yellow("\n⚠️题库为空，请先导入题目！"))
            return

        filtered = _filter_by_type(all_questions, type_label)
        if not filtered:
            print(yellow(f"\n⚠️题库中没有{type_label}！"))
            return

        total = len(filtered)
        print(f"\n  【所有科目】{type_label} - 共 {total} 道题")
        print("  输入 exit 返回菜单\n")

        random.shuffle(filtered)

        for i, question in enumerate(filtered, 1):
            _display_question(question, i, total)

            prompt = _get_answer_prompt(question)
            user_answer = input(prompt).strip()
            if user_answer.lower() == "exit":
                remaining = filtered[i-1:]
                _save_progress_on_exit("所有科目", remaining, total, "all_by_type", type_label)
                return

            is_correct = question.check_answer(user_answer)
            if is_correct:
                print(green("\n✅回答正确！"))
                record_result(question.subject, True)
            else:
                print(red("\n❌回答错误！"))
                print(f"  正确答案：{question.answer}")
                print(f"  你的答案：{user_answer}")
                record_result(question.subject, False)
                add_wrong_record(question.subject, question, user_answer)

            print()

        clear_brush_progress()
        print(green(f"✅【所有科目】{type_label}刷题完成！"))
