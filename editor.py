"""
编辑题目模块
支持查看、修改、删除已存储的题目
"""

from typing import List, Tuple
from models.question import (
    Question,
    ChoiceQuestion,
    TrueFalseQuestion,
    FillBlankQuestion,
    EssayQuestion,
)
from question_manager import (
    load_questions,
    save_questions,
    load_wrong_records,
    save_wrong_records,
)
from utils.helpers import get_subject_list


def _get_question_preview(q: Question, max_len: int = 40) -> str:
    """截取题目预览文本"""
    text = q.text.replace("\n", " ")
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _collect_all_questions() -> List[Tuple[int, str, Question]]:
    """
    收集所有科目的题目，返回列表 [(序号, 科目, Question对象)]
    序号从1开始连续编号
    """
    subjects = get_subject_list()
    all_items = []
    idx = 1
    for subj in subjects:
        questions = load_questions(subj)
        for q in questions:
            all_items.append((idx, subj, q))
            idx += 1
    return all_items


def _remove_wrong_records_for_question(subject: str, question_text: str):
    """删除指定题目的错题本记录"""
    records = load_wrong_records()
    records = [
        r
        for r in records
        if not (r.subject == subject and r.question_text == question_text)
    ]
    save_wrong_records(records)


def _edit_question(subject: str, question: Question) -> Question:
    """重新编辑题目内容，返回新的 Question 对象"""
    q_type = question.get_type_name()
    print(f"\n--- 编辑题目（原题型: {question.get_type_label()}）---")
    print("（直接回车保持不变）")

    # 修改题目文本
    old_text = question.text
    print(f"原题目: {old_text.replace(chr(10), ' / ')}")
    new_text_input = input("新题目（空行结束，直接回车跳过）:\n").strip()
    if new_text_input:
        # 多行输入支持
        text_lines = [new_text_input]
        while True:
            line = input()
            if line == "":
                break
            text_lines.append(line)
        new_text = "\n".join(text_lines)
    else:
        new_text = old_text

    if q_type == "判断题":
        old_answer = question.answer
        print(f"原答案: {old_answer}")
        new_answer = input("新答案（正确/错误 / 对/错 / t/f）: ").strip()
        if not new_answer:
            new_answer = old_answer
        return TrueFalseQuestion(text=new_text, answer=new_answer, subject=subject)

    elif q_type == "选择题":
        if isinstance(question, ChoiceQuestion):
            old_options = question.options
            old_answer = question.answer
            choice_type = question.choice_type

            print(f"原选项:")
            for label, opt_text in old_options:
                print(f"  {label}. {opt_text}")
            print("新选项（每行一个，如：A. 选项内容，输入空行结束，直接回车跳过）:")
            new_options_input = input(f"  A. ").strip()
            if new_options_input:
                options = []
                labels = ["A", "B", "C", "D", "E", "F"]
                i = 0
                while i < len(labels):
                    if i == 0:
                        opt_line = new_options_input
                    else:
                        opt_line = input(f"  {labels[i]}. ").strip()
                    if opt_line == "":
                        if i == 0:
                            print("  至少需要一个选项。")
                            continue
                        break
                    options.append((labels[i], opt_line))
                    i += 1
                if not options:
                    options = old_options
            else:
                options = old_options

            valid_labels = [o[0] for o in options]

            if choice_type == "single":
                answer = input(f"正确答案（原: {old_answer}）: ").strip().upper()
                if not answer or answer not in valid_labels:
                    answer = old_answer if old_answer in valid_labels else valid_labels[0]
                return ChoiceQuestion(
                    text=new_text, options=options, answer=answer,
                    subject=subject, choice_type="single",
                )
            else:
                answer_input = input(f"正确答案（原: {old_answer}）: ").strip().upper()
                if not answer_input:
                    answer_letters = old_answer
                else:
                    answer_letters = answer_input.replace(" ", "")
                return ChoiceQuestion(
                    text=new_text, options=options, answer=answer_letters,
                    subject=subject, choice_type="multiple",
                    multiple_answers=list(answer_letters),
                )
        else:
            print("  无法识别选择题类型，跳过修改")
            return question

    elif q_type == "填空题":
        old_answer = question.answer
        print(f"原答案: {old_answer}")
        new_answer = input("新答案: ").strip()
        if not new_answer:
            new_answer = old_answer
        return FillBlankQuestion(text=new_text, answer=new_answer, subject=subject)

    elif q_type == "简答题":
        old_answer = question.answer
        print(f"原参考答案: {old_answer}")
        new_answer = input("新参考答案: ").strip()
        if not new_answer:
            new_answer = old_answer
        return EssayQuestion(text=new_text, answer=new_answer, subject=subject)

    else:
        print("  未知题型，无法编辑")
        return question


def edit_question_menu():
    """编辑题目主菜单"""
    all_items = _collect_all_questions()
    if not all_items:
        print("\n  ⚠️ 题库为空，请先导入题目！")
        return

    print("\n" + "=" * 50)
    print("           编辑题目")
    print("=" * 50)
    print(f"  共 {len(all_items)} 道题目\n")

    # 显示题目列表
    for idx, subj, q in all_items:
        preview = _get_question_preview(q)
        print(f"  {idx:>3}. [{subj}] [{q.get_type_label()}] {preview}")
    print(f"\n  0. 返回主菜单")

    try:
        choice = input("\n请输入编号选择题目: ").strip()
        if choice == "0" or choice.lower() == "exit":
            return

        idx = int(choice)
    except ValueError:
        print("  无效输入，请输入编号。")
        return

    # 查找对应题目
    target = None
    for item in all_items:
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
        # 修改
        new_q = _edit_question(subject, question)
        # 从题库中替换
        questions = load_questions(subject)
        for i, q in enumerate(questions):
            if q.text == question.text and q.answer == question.answer:
                questions[i] = new_q
                break
        save_questions(subject, questions)
        print(f"  ✓ 题目已更新")

    elif action == "2":
        # 删除
        confirm = input(f"  确认删除该题？(y/n): ").strip().lower()
        if confirm in ("y", "yes", "是"):
            # 从题库移除
            questions = load_questions(subject)
            questions = [q for q in questions if q.text != question.text]
            save_questions(subject, questions)
            # 同步清理错题本
            _remove_wrong_records_for_question(subject, question.text)
            print(f"  ✓ 题目已删除，错题本中相关记录已清理")
        else:
            print("  取消删除")

    else:
        print("  取消操作")
