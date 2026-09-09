"""
刷题界面核心逻辑模块（v2：六题型）
===================================
- 统一驱动 run_questions()：显示 -> 逐题收集答案 -> 判分 -> 维护错题本/正确率记录/进度
- 单选/多选/判断/填空/计算：自动判分；简答：展示参考答案后由用户自评（对/错/跳过）
- 填空：题干含多个【N】空位时按空逐空收集；整串模式(whole)只收集一次
- 任意输入框输入 exit 可随时退出并保存剩余进度
"""

import random
from typing import List, Optional, Callable

from models.question import (
    Question, ChoiceQuestion, TrueFalseQuestion, FillBlankQuestion, EssayQuestion,
)
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
    """按题型标签返回 Question 子类；“选择题”= 单选+多选的总称（v2 兼容过滤）"""
    _TYPE_MAP = {
        "填空题": FillBlankQuestion,
        "选择题": ChoiceQuestion,
        "判断题": TrueFalseQuestion,
    }
    return _TYPE_MAP.get(type_label)


def _filter_by_type(questions: List[Question], type_label: str) -> List[Question]:
    q_class = _get_type_class(type_label)
    if q_class is None:
        return questions
    return [q for q in questions if isinstance(q, q_class)]


def _fmt_user_answer(user_answer) -> str:
    if isinstance(user_answer, (list, tuple)):
        return " ｜ ".join(str(x) if str(x) else "（空）" for x in user_answer)
    return str(user_answer)


# ---------------------------------------------------------------- 单题交互 ----------------------------------------------------------------

def _collect_answer(question: Question):
    """
    收集一道题的作答内容。
    返回 (user_answer, exited)：
      user_answer 可能是 str / list[str]（多空）；简答返回文本。
      exited=True 表示用户输入了 exit，需结束本次刷题。
    """
    if isinstance(question, FillBlankQuestion) and not question.whole_string:
        n = question.blank_count()
        if n > 1:
            vals = []
            for k in range(1, n + 1):
                s = input(f"  第{k}空答案（回车留空；输入 exit 结束刷题）: ").strip()
                if s.lower() == "exit":
                    return None, True
                vals.append(s)
            return vals, False

    if isinstance(question, EssayQuestion):
        print(yellow("  （本题为简答题，不自动判分。请作答，空行结束输入；输入 exit 结束刷题）"))
        lines = []
        while True:
            try:
                line = input("  > ").rstrip()
            except (EOFError, KeyboardInterrupt):
                return None, True
            if line.lower() == "exit":
                return None, True
            if line == "" and lines:
                break
            lines.append(line)
        return "\n".join(lines).strip(), False

    prompt = _get_answer_prompt(question)
    try:
        s = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None, True
    if s.lower() == "exit":
        return None, True
    return s, False


def _get_answer_prompt(question: Question) -> str:
    if isinstance(question, ChoiceQuestion) and question.choice_type == "multiple":
        return "  请输入答案（如：A C D，答案之间用空格隔开）: "
    if isinstance(question, TrueFalseQuestion):
        return "  请选择答案（正确/错误 / 对/错 / t/f）: "
    if isinstance(question, FillBlankQuestion) and question.whole_string:
        return "  请输入完整答案: "
    return "  请输入答案: "


def _show_feedback(question: Question, user_answer, correct: bool):
    if correct:
        print(green("\n✅ 回答正确！"))
    else:
        print(red("\n❌ 回答错误！"))
        print(f"  正确答案：{question.answer_text()}")
        print(f"  你的答案：{_fmt_user_answer(user_answer)}")


def _essay_self_grade(question: Question):
    """简答自评：返回 (correct, skipped)；None 表示输入 exit"""
    print("\n  —— 参考答案 ——")
    print(f"  {question.answer_text() or '（无参考答案）'}")
    try:
        verdict = input("\n  请对照参考答案自行判定：答对(y)/答错(n)/跳过不计(直接回车；输入 exit 结束) : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None, False
    if verdict == "exit":
        return None, True
    if verdict in ("y", "yes", "对", "对"):
        return True, False
    if verdict in ("n", "no", "错", "x", "错误"):
        return False, False
    return None, False  # skipped


def _process_one(question: Question, wrong_mode: bool, book_subject: str = None):
    """
    处理一道题（收集+判分+错题本+记录）。
    返回 (exited, answered)：exited=True 表示用户 exit 需退出；answered 表示本题是否已完成作答。
    """
    book_subject = book_subject or question.subject

    # ---- 简答题：不自动判分，走自评 ----
    if isinstance(question, EssayQuestion):
        user_answer, exited = _collect_answer(question)
        if exited:
            return True, False
        print("\n  你的答案：")
        print(f"  {_fmt_user_answer(user_answer)}")
        correct, exited = _essay_self_grade(question)
        if exited:
            return True, True  # 已作答后退出，本题不再重答
        if correct is None:  # 跳过：不计入统计与错题本
            print(yellow("  （已跳过判分，本题不计入统计）"))
            return False, True
        if correct:
            print(green("✅ 自评：答对"))
            record_result(book_subject, True)
            if wrong_mode:
                remove_wrong_record(question.subject, question.text)
        else:
            print(red("❌ 自评：答错"))
            record_result(book_subject, False)
            if wrong_mode:
                update_wrong_record_timestamp(question.subject, question.text)
            else:
                add_wrong_record(book_subject, question, _fmt_user_answer(user_answer))
        return False, True

    # ---- 其它题型：自动判分 ----
    user_answer, exited = _collect_answer(question)
    if exited:
        return True, False
    is_correct = question.check_answer(user_answer)
    if is_correct:
        _show_feedback(question, user_answer, True)
        record_result(book_subject, True)
        if wrong_mode:
            remove_wrong_record(question.subject, question.text)
    else:
        _show_feedback(question, user_answer, False)
        record_result(book_subject, False)
        if wrong_mode:
            update_wrong_record_timestamp(question.subject, question.text)
        else:
            add_wrong_record(book_subject, question, _fmt_user_answer(user_answer))
    return False, True


# ---------------------------------------------------------------- 统一会话驱动 ----------------------------------------------------------------

def run_questions(questions: List[Question], *, header: str = "",
                  wrong_mode: bool = False, book_subject_of: Callable = None,
                  mode_key: str = "all"):
    """
    统一刷题驱动：遍历题目、作答、判分；exit 时保存剩余进度并退出。
    questions: 待刷题目（已打乱）
    header: 开场文案（含题数说明）
    wrong_mode: 错题复习模式（答对移除、答错更新该错题时间戳）
    book_subject_of: 统计科目取值函数，默认取 q.subject
    """
    total = len(questions)
    if header:
        print(header)
    print("  输入 exit 可随时退出（进度会自动保存）\n")

    for i, question in enumerate(questions, 1):
        print("-" * 50)
        print(f"  题目 {i}/{total}")
        print(question.display())
        print()
        book_subject = book_subject_of(question) if book_subject_of else question.subject
        exited, answered = _process_one(question, wrong_mode=wrong_mode, book_subject=book_subject)
        print()
        if exited:
            # 未作答则本题仍算剩余；已作答则从下一题开始
            remaining = questions[i:] if answered else questions[i - 1:]
            if remaining:
                _save_progress_on_exit(header_subject(questions), remaining, total, mode_key)
            return

    clear_brush_progress()
    print(green(f"✅ 本次刷题完成！"))


def header_subject(questions: List[Question]) -> str:
    subs = {q.subject for q in questions}
    return "所有科目" if len(subs) > 1 else (next(iter(subs)) if subs else "")


def _save_progress_on_exit(subject: str, remaining: List[Question], total: int, mode_key: str):
    remaining_data = [{"subject": q.subject, "text": q.text} for q in remaining]
    save_brush_progress({
        "subject": subject,
        "mode": mode_key,
        "type_label": None,
        "remaining": remaining_data,
        "total": total,
    })
    print(yellow("\n⚠️ 进度已保存，可使用「继续答题」接着刷。"))


# ---------------------------------------------------------------- 入口（兼容 menu.py 旧签名） ----------------------------------------------------------------

def _shuffle(seq):
    seq = list(seq)
    random.shuffle(seq)
    return seq


def _wrong_questions(subject: str):
    """从错题本重建题目列表（按科目；找不到题目的记录跳过）"""
    records = get_wrong_records_by_subject(subject)
    bank = {}
    out = []
    for r in records:
        if r.subject not in bank:
            bank[r.subject] = load_questions(r.subject)
        q = next((x for x in bank[r.subject] if x.text == r.question_text), None)
        if q is not None:
            out.append(q)
    return out


def start_brushing(subject: str, only_wrong: bool = False):
    if only_wrong:
        qs = _wrong_questions(subject)
        if not qs:
            print(f"{yellow(f'⚠️【{subject}】错题本为空，无需复习！')}")
            return
        run_questions(_shuffle(qs), header=f"\n  【{subject}】错题复习 - 共 {len(qs)} 道错题",
                      wrong_mode=True, mode_key="wrong")
    else:
        qs = load_questions(subject)
        if not qs:
            print(f"{yellow(f'⚠️【{subject}】题库为空，请先导入题目！')}")
            return
        run_questions(_shuffle(qs), header=f"\n  【{subject}】刷题 - 共 {len(qs)} 道题", mode_key="all")


def start_brushing_all(only_wrong: bool = False, subjects: List[str] = None):
    if subjects is None:
        from utils.helpers import get_subject_list
        subjects = get_subject_list()
    if only_wrong:
        qs = []
        for subj in subjects:
            qs += _wrong_questions(subj)
        if not qs:
            print(yellow("⚠️ 所有科目的错题本均为空，无需复习！"))
            return
        run_questions(_shuffle(qs), header=f"\n  【所有科目】错题复习 - 共 {len(qs)} 道错题",
                      wrong_mode=True, mode_key="all_wrong")
    else:
        qs = []
        for subj in subjects:
            qs += load_questions(subj)
        if not qs:
            print(yellow("\n⚠️ 题库为空，请先导入题目！"))
            return
        run_questions(_shuffle(qs), header=f"\n  【所有科目】混合刷题 - 共 {len(qs)} 道题", mode_key="all")


def start_brushing_by_type(subject: str, type_label: str, only_wrong: bool = False):
    if only_wrong:
        qs = _wrong_questions(subject)
        filtered = [q for q in qs if _match_wrong_type(q, type_label)]
        if not filtered:
            print(f"{yellow(f'⚠️【{subject}】错题本中没有{type_label}！')}")
            return
        run_questions(_shuffle(filtered), header=f"\n  【{subject}】{type_label} - 错题复习 - 共 {len(filtered)} 道题",
                      wrong_mode=True, mode_key="by_type_wrong")
    else:
        qs = load_questions(subject)
        filtered = _filter_by_type(qs, type_label)
        if not filtered:
            print(f"{yellow(f'⚠️【{subject}】题库中没有{type_label}！')}")
            return
        run_questions(_shuffle(filtered), header=f"\n  【{subject}】{type_label} - 共 {len(filtered)} 道题",
                      mode_key="by_type")


def start_brushing_all_by_type(type_label: str, only_wrong: bool = False,
                               subjects: List[str] = None):
    if subjects is None:
        from utils.helpers import get_subject_list
        subjects = get_subject_list()
    if only_wrong:
        qs = []
        for subj in subjects:
            qs += _wrong_questions(subj)
        filtered = [q for q in qs if _match_wrong_type(q, type_label)]
        if not filtered:
            print(yellow(f"⚠️ 所有科目的错题本中没有{type_label}！"))
            return
        run_questions(_shuffle(filtered), header=f"\n  【所有科目】{type_label} - 错题复习 - 共 {len(filtered)} 道题",
                      wrong_mode=True, mode_key="all_by_type_wrong")
    else:
        qs = []
        for subj in subjects:
            qs += load_questions(subj)
        filtered = _filter_by_type(qs, type_label)
        if not filtered:
            print(yellow(f"⚠️ 所有科目题库中没有{type_label}！"))
            return
        run_questions(_shuffle(filtered), header=f"\n  【所有科目】{type_label} - 共 {len(filtered)} 道题",
                      mode_key="all_by_type")


def _match_wrong_type(q: Question, type_label: str) -> bool:
    """错题记录按题型过滤：选择题 = 单选+多选"""
    if isinstance(q, ChoiceQuestion):
        return type_label in ("选择题", q.get_type_name())
    return q.get_type_name() == type_label or q.get_type_label() == type_label


# ---------------------------------------------------------------- 继续答题 ----------------------------------------------------------------

def resume_brushing():
    progress = load_brush_progress()
    if not progress:
        print(yellow("⚠️ 当前没有可继续的刷题进度！"))
        return
    remaining_data = progress.get("remaining", [])
    total = progress.get("total", 0)
    subject = progress.get("subject", "")

    remaining = []
    banks = {}
    for item in remaining_data:
        subj = item.get("subject", subject)
        text = item.get("text", "")
        if subj not in banks:
            banks[subj] = load_questions(subj)
        q = next((x for x in banks[subj] if x.text == text), None)
        if q:
            remaining.append(q)
    if not remaining:
        print(yellow("⚠️ 进度文件中的题目均已不存在，进度已清除。"))
        clear_brush_progress()
        return

    mode = progress.get("mode", "all")
    wrong = str(mode).endswith("wrong")
    done = total - len(remaining)
    print(f"\n  【继续答题】- 剩余 {len(remaining)} 题（已答 {done}/{total}）")
    run_questions(remaining, wrong_mode=wrong, mode_key=mode)
