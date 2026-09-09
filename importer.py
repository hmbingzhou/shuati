"""
导入题目界面模块
支持同一题型的连续导入模式
"""

from models.question import (
    TrueFalseQuestion,
    ChoiceQuestion,
    FillBlankQuestion,
)
from question_manager import add_question


# 退出指令集合：用户输入这些指令时返回上级菜单
_BACK_CMDS = {"back", "menu", "esc", "exit"}


def _is_back_cmd(text: str) -> bool:
    """判断是否为返回指令"""
    return text.strip().lower() in _BACK_CMDS


def import_questions(subject: str):
    """科目题目的导入流程"""
    print(f"\n{'='*50}")
    print(f"  开始导入【{subject}】题目")
    print(f"  输入 back 或 exit 可随时返回上级菜单")
    print(f"{'='*50}")

    while True:
        print("\n请选择题型：")
        print("  1. 判断题")
        print("  2. 单选题")
        print("  3. 多选题")
        print("  4. 填空题")
        print("  5. 简答题")
        print("  0. 返回上级菜单")

        choice = input("\n请输入编号: ").strip()
        if choice == "0" or choice.lower() in _BACK_CMDS:
            break

        if choice == "1":
            _import_true_false(subject)
        elif choice == "2":
            _import_single_choice(subject)
        elif choice == "3":
            _import_multiple_choice(subject)
        elif choice == "4":
            _import_fill_blank(subject)
        elif choice == "5":
            _import_essay(subject)
        else:
            print("  无效选择，请重新输入。")

    print(f"  【{subject}】导入结束。")


def _import_true_false(subject: str):
    """导入判断题（连续导入模式）"""
    print("\n--- 导入判断题（连续导入模式）---")
    print("提示：输入 back 可随时返回题型菜单")
    count = 0

    while True:
        count += 1
        print(f"\n--- 第{count}题 ---")
        print("输入题目（空行结束）:")
        text_lines = []
        while True:
            line = input()
            if _is_back_cmd(line):
                return
            if line == "":
                break
            text_lines.append(line)
        if not text_lines:
            print("  取消导入，返回题型菜单")
            return
        text = "\n".join(text_lines)

        answer_raw = input("答案（正确/错误 / 对/错 / t/f / true/false）: ").strip()
        if _is_back_cmd(answer_raw):
            return

        # 利用 TrueFalseQuestion 的 __init__ 自动标准化
        q = TrueFalseQuestion(text=text, answer=answer_raw, subject=subject)
        # 检查答案是否有效（标准化后仍是原值说明不合法）
        if q.answer not in ("正确", "错误"):
            print(f'  无效答案，请输入"正确/错误/对/错/t/f/true/false"')
            count -= 1  # 不计入已导入数
            continue

        add_question(subject, q)
        print(f"  ✓ 第{count}题已导入，继续输入下一题（输入 back 返回题型菜单）")


def _import_choice_common(subject: str, choice_type: str):
    """
    导入选择题的连续导入流程（单选题/多选题共用输入逻辑）
    choice_type: "single" 或 "multiple"
    """
    type_label = "单选题" if choice_type == "single" else "多选题"
    print(f"\n--- 导入{type_label}（连续导入模式）---")
    print("提示：输入 back 可随时返回题型菜单")
    count = 0

    while True:
        count += 1
        print(f"\n--- 第{count}题 ---")
        print("输入题目（空行结束）:")
        text_lines = []
        while True:
            line = input()
            if _is_back_cmd(line):
                return
            if line == "":
                break
            text_lines.append(line)
        if not text_lines:
            print("  取消导入，返回题型菜单")
            return
        text = "\n".join(text_lines)

        print("输入选项（每行一个，如：A. 选项内容，输入空行结束）:")
        options = []
        labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"]
        i = 0
        while i < len(labels):
            opt_line = input(f"  {labels[i]}. ")
            if _is_back_cmd(opt_line):
                return
            if opt_line.strip() == "":
                if i == 0:
                    print("  至少需要一个选项。")
                    continue
                break
            options.append((labels[i], opt_line.strip()))
            i += 1

        if not options:
            print("  取消导入，返回题型菜单")
            return

        valid_labels = [opt[0] for opt in options]

        if choice_type == "single":
            answer = input("正确答案（请输入选项字母，如 A）: ").strip().upper()
            if _is_back_cmd(answer):
                return
            if answer not in valid_labels:
                print(f"  无效答案，请输入 {', '.join(valid_labels)} 中的一个。")
                count -= 1
                continue
            q = ChoiceQuestion(
                text=text, options=options, answer=answer, subject=subject,
                choice_type="single",
            )
        else:
            answer_input = input("正确答案（请输入选项字母，如 A B D 或 ABD）: ").strip().upper()
            if _is_back_cmd(answer_input):
                return
            # 解析答案，支持 "A B D" 或 "ABD" 格式
            answer_letters = answer_input.replace(" ", "")
            # 验证每个选项是否有效
            answer_list = list(answer_letters)
            invalid = [a for a in answer_list if a not in valid_labels]
            if invalid:
                print(f"  无效答案选项: {', '.join(invalid)}，请输入 {', '.join(valid_labels)} 中的选项。")
                count -= 1
                continue
            if not answer_list:
                print("  答案不能为空。")
                count -= 1
                continue
            if len(answer_list) < 2:
                print("  多选题至少需要两个正确答案。")
                count -= 1
                continue
            q = ChoiceQuestion(
                text=text, options=options, answer=answer_letters, subject=subject,
                choice_type="multiple",
                multiple_answers=answer_list,
            )

        add_question(subject, q)
        print(f"  ✓ 第{count}题已导入，继续输入下一题（输入 back 返回题型菜单）")


def _import_single_choice(subject: str):
    """导入单选题（连续导入模式）"""
    _import_choice_common(subject, "single")


def _import_multiple_choice(subject: str):
    """导入多选题（连续导入模式）"""
    _import_choice_common(subject, "multiple")


def _import_fill_blank(subject: str):
    """导入填空题（连续导入模式）"""
    print("\n--- 导入填空题（连续导入模式）---")
    print("提示：输入 back 可随时返回题型菜单")
    print("题目文本中，空行位置将自动替换为 ______（连续输入两个空行结束题目输入）")
    count = 0

    while True:
        count += 1
        print(f"\n--- 第{count}题 ---")
        text_lines = []
        blank_count = 0
        while True:
            line = input()
            if _is_back_cmd(line):
                return
            if line == "":
                blank_count += 1
                if blank_count >= 1:
                    break
                #text_lines.append("______")
            else:
                blank_count = 0
                text_lines.append(line)

        if not text_lines:
            print("  取消导入，返回题型菜单")
            return
        text = "\n".join(text_lines)

        answer = input("答案: ").strip()
        if _is_back_cmd(answer):
            return
        if not answer:
            print("  答案不能为空。")
            count -= 1
            continue

        q = FillBlankQuestion(text=text, answer=answer, subject=subject)
        add_question(subject, q)
        print(f"  ✓ 第{count}题已导入，继续输入下一题（输入 back 返回题型菜单）")


def _import_essay(subject: str):
    """导入简答题（连续导入模式，扩展预留）"""
    from models.question import EssayQuestion

    print("\n--- 导入简答题（连续导入模式）---")
    print("提示：输入 back 可随时返回题型菜单")
    count = 0

    while True:
        count += 1
        print(f"\n--- 第{count}题 ---")
        print("输入题目（空行结束）:")
        text_lines = []
        while True:
            line = input()
            if _is_back_cmd(line):
                return
            if line == "":
                break
            text_lines.append(line)
        if not text_lines:
            print("  取消导入，返回题型菜单")
            return
        text = "\n".join(text_lines)

        answer = input("参考答案: ").strip()
        if _is_back_cmd(answer):
            return
        if not answer:
            print("  答案不能为空。")
            count -= 1
            continue

        q = EssayQuestion(text=text, answer=answer, subject=subject)
        add_question(subject, q)
        print(f"  ✓ 第{count}题已导入，继续输入下一题（输入 back 返回题型菜单）")
