"""
题目模型模块（存储格式 v2）
============================
v2 统一六种题型：单选题 / 多选题 / 判断题 / 填空题 / 简答题 / 计算题

- 单选、多选、判断：题干(text) + 选项(选择题才有 options) + 图片(内嵌文件名) + 答案
- 填空、简答、计算：题干 + 图片 + 答案（无选项）
- 图片统一「内嵌文件名 token」显示（如 1.png / ![](1.png)），并自动收集到 images 字段
- 填空题：
    · 题干里用 【N】 标记第 N 个空（编辑器自动编号）；
    · 答案 = {items:[{accept:[...], group: 可选}]}，accept 为该空可接受答案集合，
      同一 group 的空位可以任意调换顺序（组内多重集比对）；
    · 兼容 v1 旧数据（answer 为字符串、空位为 （　　）/____ 等）由加载器与迁移工具处理。
- 简答题不自动判分（由前端展示参考答案、用户自评）；计算题严格判分（数值可比则按容差）。

文件同时兼容旧（v1）文件读取：
    type=选择题 + choice_type + multiple_answers
    type=填空题 answer 为整串字符串
"""

import itertools
import re
from abc import ABC, abstractmethod
from utils.helpers import yellow

# ---------------------------------------------------------------- 常量 ----------------------------------------------------------------

TYPE_ORDER = ("单选题", "多选题", "判断题", "填空题", "简答题", "计算题")
AUTO_GRADED_TYPES = ("单选题", "多选题", "判断题", "填空题", "计算题")

# 题干里图片文件名 token（png/jpg 等）。
# - 支持科目前缀相对路径：数据结构/3.png、_shared/5a.png，或扁平短名 1.png
# - 行内精确插图用方括号标记：[数据结构/3.png]（旧数据也允许无括号裸路径）
_IMG_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_\u4e00-\u9fff./-]+\.(?:png|jpe?g|gif|bmp|webp)", re.IGNORECASE)
BRACKET_IMG_RE = re.compile(
    r"\[([A-Za-z0-9_\u4e00-\u9fff./-]+\.(?:png|jpe?g|gif|bmp|webp))\]", re.IGNORECASE)

# 填空空位编号标记：【1】【12】……
BLANK_MARK_RE = re.compile(r"【\s*(\d+)\s*】")


def _mask_bracketed(s):
    """把 [图片路径] 片段替换为等长空格（避免裸路径正则二次命中）"""
    return BRACKET_IMG_RE.sub(lambda m: " " * (m.end() - m.start()), s)


def collect_image_tokens(*texts) -> list:
    """从若干文本里收集图片路径（支持 [路径] 与旧裸路径；按出现顺序去重）"""
    seen, out = set(), []
    for t in texts:
        if not t:
            continue
        t = str(t)
        for m in BRACKET_IMG_RE.finditer(t):
            token = m.group(1)
            if token not in seen:
                seen.add(token)
                out.append(token)
        masked = _mask_bracketed(t)
        for m in _IMG_TOKEN_RE.finditer(masked):
            token = m.group(0)
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def mask_image_tokens(text: str) -> str:
    """把文本里的行内图片标记统一替换为 （图），供终端/纯文本预览使用（不暴露文件名）"""
    t = str(text or "")
    t = BRACKET_IMG_RE.sub("（图）", t)
    t = _IMG_TOKEN_RE.sub("（图）", t)
    return t


def normalize_user_text(s: str) -> str:
    """文本答案统一入口：仅去首尾空白（严格判分；不忽略大小写/全半角）"""
    return str(s or "").strip()


# ---------------------------------------------------------------- 基类 ----------------------------------------------------------------

class Question(ABC):
    """题目抽象基类（v2 公共字段：type/text/images/subject/flags + 各类 answer）"""

    def __init__(self, text: str, answer, subject: str = ""):
        self.text = str(text or "")
        self.answer = answer
        self.subject = subject
        self.flag_star = False   # 网页版标记：黄色星星
        self.flag_cross = False  # 网页版标记：红色叉
        self.images = []         # “题后配图”：显示在题干文字之后的图片相对路径列表（行内图用 [路径] 写在 text 里）

    # ---- 类型 ----
    @abstractmethod
    def get_type_name(self) -> str:
        """题型存储名（单选题/多选题/判断题/填空题/简答题/计算题）"""
        pass

    def get_type_label(self) -> str:
        """展示标签：v2 与存储名一致"""
        return self.get_type_name()

    def is_auto_graded(self) -> bool:
        """是否自动判分（简答题 False，走自评）"""
        return True

    # ---- 显示 ----
    @abstractmethod
    def display(self) -> str:
        pass

    def answer_text(self) -> str:
        """人类可读的标准答案（终端提示/网页反馈/错题本快照共用）"""
        return str(self.answer if self.answer is not None else "")

    # ---- 判分 ----
    @abstractmethod
    def check_answer(self, user_answer) -> bool:
        """判分。填空接受 list[str]（每空一个）或 str（单空兼容）"""
        pass

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        d = {
            "type": self.get_type_name(),
            "text": self.text,
            "answer": self._answer_to_json(),
            "subject": self.subject,
            "images": [str(x) for x in (self.images or [])],
            "flag_star": bool(self.flag_star),
            "flag_cross": bool(self.flag_cross),
        }
        return d

    def _answer_to_json(self):
        return self.answer

    def _extra_image_texts(self) -> list:
        """子类额外的图片来源文本（如选项文本，供收集/迁移用）"""
        return []

    @staticmethod
    def from_dict(data: dict) -> "Question":
        q_type = str(data.get("type") or "")
        if q_type == "选择题":  # v1 旧数据：按 choice_type 分发到单选/多选
            if str(data.get("choice_type", "single")).lower() == "multiple":
                q = MultipleChoiceQuestion.from_dict(data)
            else:
                q = SingleChoiceQuestion.from_dict(data)
        else:
            klass = QuestionFactory.get_class(q_type)
            if klass is None:
                raise ValueError(f"未知题型: {q_type}")
            q = klass.from_dict(data)
        q.flag_star = bool(data.get("flag_star", False))
        q.flag_cross = bool(data.get("flag_cross", False))
        imgs = data.get("images")
        q.images = [str(x) for x in (imgs if isinstance(imgs, list) else [])]
        return q


# ---------------------------------------------------------------- 选择题 ----------------------------------------------------------------

class ChoiceQuestion(Question):
    """
    选择题公共基类（单选/多选共用字段）。
    v2 中不注册为独立题型；保留以便兼容 convert_tools 等旧代码直接构造。
    """

    def __init__(self, text: str, options: list, answer: str,
                 subject: str = "", choice_type: str = "single",
                 multiple_answers: list = None):
        super().__init__(text, str(answer or "").upper().replace(" ", ""), subject)
        self.options = options or []   # [["A", 文本], ...]
        self._choice_type = "single" if choice_type != "multiple" else "multiple"
        if not self.answer and multiple_answers:
            self.answer = "".join(str(x) for x in multiple_answers)

    @property
    def choice_type(self) -> str:
        """按实际子类派生的单选/多选属性（兼容 convert_tools 等旧用法）"""
        if isinstance(self, MultipleChoiceQuestion):
            return "multiple"
        if isinstance(self, SingleChoiceQuestion):
            return "single"
        return self._choice_type

    def check_answer(self, user_answer) -> bool:
        """默认实现：单选逐字比较；多选集合比较（供直接构造的旧代码使用）"""
        if self.choice_type == "multiple":
            valid = set(self.option_letters)
            user_set = set(re.sub(r"[^A-Za-z]", "", str(user_answer or "")).upper())
            if not user_set or not user_set.issubset(valid):
                return False
            return user_set == set(self.answer)
        return normalize_user_text(user_answer).upper() == self.answer.upper()

    @property
    def option_letters(self) -> list:
        return [str(o[0]).upper() for o in self.options
                if isinstance(o, (list, tuple)) and o]

    def get_type_name(self) -> str:
        return "多选题" if self.choice_type == "multiple" else "单选题"

    def display(self) -> str:
        lines = [f"{yellow(f'[{self.get_type_label()}]')} {mask_image_tokens(self.text)}"]
        for label_opt, option_text in self.options:
            lines.append(f"  {label_opt}. {mask_image_tokens(option_text)}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["options"] = [list(o) for o in (self.options or [])]
        return d

    def _extra_image_texts(self) -> list:
        return [t for _, t in self.options]

    @staticmethod
    def from_dict(data: dict, choice_type: str = None) -> "ChoiceQuestion":
        ct = choice_type or data.get("choice_type", "single")
        if str(ct).lower() == "multiple":
            return MultipleChoiceQuestion.from_dict(data)
        return SingleChoiceQuestion.from_dict(data)


class SingleChoiceQuestion(ChoiceQuestion):
    """单选题"""

    def get_type_name(self) -> str:
        return "单选题"

    def check_answer(self, user_answer) -> bool:
        return normalize_user_text(user_answer).upper() == self.answer.upper()

    @staticmethod
    def from_dict(data: dict) -> "SingleChoiceQuestion":
        return SingleChoiceQuestion(
            text=data.get("text", ""),
            options=data.get("options") or [],
            answer=data.get("answer", ""),
            subject=data.get("subject", ""),
        )


class MultipleChoiceQuestion(ChoiceQuestion):
    """多选题：答案字母集合相等（全对才判对，忽略顺序与大小写）"""

    def get_type_name(self) -> str:
        return "多选题"

    def check_answer(self, user_answer) -> bool:
        valid = set(self.option_letters)
        user_set = set(re.sub(r"[^A-Za-z]", "", str(user_answer or "")).upper())
        if not user_set or not user_set.issubset(valid):
            return False
        return user_set == set(self.answer)

    @staticmethod
    def from_dict(data: dict) -> "MultipleChoiceQuestion":
        answer = str(data.get("answer") or "")
        if not answer and data.get("multiple_answers"):
            answer = "".join(str(x) for x in data["multiple_answers"])
        return MultipleChoiceQuestion(
            text=data.get("text", ""),
            options=data.get("options") or [],
            answer=answer,
            subject=data.get("subject", ""),
        )


# ---------------------------------------------------------------- 判断题 ----------------------------------------------------------------

class TrueFalseQuestion(Question):
    """判断题：不存选项，答案固定 正确/错误（兼容 对/错/t/f/√× 等输入）"""

    TF_MAP = {
        "对": "正确", "正确": "正确", "t": "正确", "true": "正确", "√": "正确", "v": "正确", "y": "正确", "yes": "正确",
        "错": "错误", "错误": "错误", "f": "错误", "false": "错误", "×": "错误", "x": "错误", "n": "错误", "no": "错误",
    }

    def __init__(self, text: str, answer: str, subject: str = ""):
        super().__init__(text, self._normalize(answer), subject)

    @classmethod
    def _normalize(cls, val: str) -> str:
        return cls.TF_MAP.get(str(val or "").strip().lower(), str(val or "").strip())

    def get_type_name(self) -> str:
        return "判断题"

    def display(self) -> str:
        return f"{yellow('[判断题]')} {mask_image_tokens(self.text)}\n  请选择：正确 / 错误"

    def check_answer(self, user_answer) -> bool:
        return self._normalize(user_answer) == self.answer

    @staticmethod
    def from_dict(data: dict) -> "TrueFalseQuestion":
        return TrueFalseQuestion(
            text=data.get("text", ""),
            answer=data.get("answer", ""),
            subject=data.get("subject", ""),
        )


# ---------------------------------------------------------------- 填空题 ----------------------------------------------------------------

class FillBlankQuestion(Question):
    """
    填空题
    - 题干空位标记：【1】【2】…
    - 标准答案：self.answer = [{"accept":[...], "group": 可选 int|None}, ...]
      下标 i 对应题干【i+1】
    - 判分：同一 group 的空位整组可换序（组内多重集匹配）；无组/不同组按位比对
    - 兼容 v1 旧 answer 字符串：能按空位数拆则拆，否则整串作为唯一空答案
    """

    def __init__(self, text: str, answer=None, subject: str = ""):
        super().__init__(text, answer, subject)
        self.whole_string = False  # 整串答案模式（旧数据降级）：内部空位标记只作展示，按整串比对
        if isinstance(self.answer, str):
            self.answer = self._from_legacy_string(self.answer)
        elif isinstance(self.answer, dict):
            self.whole_string = bool(self.answer.get("whole", False))
            _items = self.answer.get("items")
            if isinstance(_items, list):  # 兼容空列表
                self.answer = _items
            else:
                self.answer = self.answer
        self.answer = [dict(x) for x in (self.answer or [])]

    # ---- 空位 ----
    def get_type_name(self) -> str:
        return "填空题"

    def _answer_to_json(self):
        out = {"items": [dict(x) for x in self.answer]}
        if self.whole_string:
            out["whole"] = True
        return out

    def blank_count(self) -> int:
        """题干空位总数；整串模式恒为 1（按整串作答）"""
        if self.whole_string:
            return 1
        nums = [int(m) for m in BLANK_MARK_RE.findall(self.text or "")]
        if nums:
            return max(nums)
        return len(self.answer) or 1

    def _answer_items(self) -> list:
        n = self.blank_count()
        items = list(self.answer)
        while len(items) < n:
            items.append({"accept": []})
        return items[:n]

    def _from_legacy_string(self, raw: str) -> list:
        """v1：答案整串（多空以空白隔开）→ 逐空 accept"""
        s = str(raw or "").strip()
        nums = [int(x) for x in BLANK_MARK_RE.findall(self.text or "")]
        n_marks = max(nums, default=0)
        n_paren = len(re.findall(r"[（(]\s{1,}[）)]", self.text or ""))
        n = max(n_marks, n_paren, 1)
        tokens = re.split(r"\s+", s) if s else []
        if len(tokens) >= n:
            items = [{"accept": [t]} for t in tokens[:max(n - 1, 0)]]
            rest = " ".join(tokens[n - 1:]) if n > 0 else s
            items.append({"accept": [rest]})
            return items
        return [{"accept": [s]}]  # 拆不开：整串作为唯一空答案（保守）

    # ---- 显示 ----
    def display(self) -> str:
        shown = self.text or ""
        if not self.whole_string:
            shown = BLANK_MARK_RE.sub(lambda m: "＿＿＿＿", shown)
        return f"{yellow('[填空题]')} {mask_image_tokens(shown)}"

    def answer_text(self) -> str:
        if self.whole_string:
            acc = (self.answer[0].get("accept") or []) if self.answer else []
            return "参考答案: " + (" / ".join(str(a) for a in acc) if acc else "（无）")
        items = self._answer_items()
        groups = {}
        for i, it in enumerate(items, 1):
            g = it.get("group")
            groups.setdefault(("g" if g is not None else None, g), []).append(i)
        parts = []
        for (kind, _g), idxs in groups.items():
            for i in idxs:
                acc = items[i - 1].get("accept") or []
                accept_txt = "/".join(str(a) for a in acc) or "？"
                suffix = "（可与同组互换）" if kind == "g" else ""
                parts.append(f"第{i}空: {accept_txt}{suffix}")
        return "；".join(parts) if parts else "（无标准答案）"

    def check_answer(self, user_answer) -> bool:
        items = self._answer_items()
        n = len(items)
        if isinstance(user_answer, str):
            if n == 1:
                vals = [normalize_user_text(user_answer)]
            else:
                vals = [x for x in (normalize_user_text(t) for t in user_answer.split(" ")) if x != ""]
        elif isinstance(user_answer, (list, tuple)):
            vals = [normalize_user_text(x) for x in user_answer]
        else:
            return False
        if len(vals) != n:
            return False
        by_group = {}
        for i, it in enumerate(items):
            by_group.setdefault(it.get("group"), []).append(i)
        done = [False] * n
        for g, positions in by_group.items():
            if g is None or len(positions) < 2:
                continue
            # 组内可换序：positions[i] 空位拿到 vals[positions[i]]；
            # 遍历这些值到组内空位的所有落位排列，只要存在“每值 ∈ 落位 accept”即对
            vals_in = [vals[i] for i in positions]
            ok = False
            for perm in itertools.permutations(positions):
                if all(vals_in[k] in {str(a).strip() for a in items[p].get("accept") or []}
                       for k, p in enumerate(perm)):
                    ok = True
                    break
            if not ok:
                return False
            for p in positions:
                done[p] = True
        for i, it in enumerate(items):
            if done[i]:
                continue
            accept = {str(a).strip() for a in it.get("accept") or []}
            if vals[i] not in accept:
                return False
        return True

    @staticmethod
    def from_dict(data: dict) -> "FillBlankQuestion":
        return FillBlankQuestion(
            text=data.get("text", ""),
            answer=data.get("answer"),
            subject=data.get("subject", ""),
        )


# ---------------------------------------------------------------- 简答题 ----------------------------------------------------------------

class EssayQuestion(Question):
    """简答题：不自动判分（自评模式），answer 存参考答案文本"""

    def get_type_name(self) -> str:
        return "简答题"

    def is_auto_graded(self) -> bool:
        return False

    def display(self) -> str:
        return f"{yellow('[简答题]')} {mask_image_tokens(self.text)}"

    def check_answer(self, user_answer) -> bool:
        return False  # 不自动判分；由界面走自评流程

    @staticmethod
    def from_dict(data: dict) -> "EssayQuestion":
        return EssayQuestion(
            text=data.get("text", ""),
            answer=data.get("answer", ""),
            subject=data.get("subject", ""),
        )


# ---------------------------------------------------------------- 计算题 ----------------------------------------------------------------

class CalculationQuestion(Question):
    """计算题：严格判分；双方均可解析为数字时按容差比较，否则 trim 后逐字比较"""

    NUM_TOLERANCE = 1e-9

    def get_type_name(self) -> str:
        return "计算题"

    def display(self) -> str:
        return f"{yellow('[计算题]')} {mask_image_tokens(self.text)}"

    def answer_text(self) -> str:
        return str(self.answer or "")

    def check_answer(self, user_answer) -> bool:
        u = normalize_user_text(user_answer)
        a = normalize_user_text(self.answer)
        if u == "" or a == "":
            return u == a
        try:
            un, an = float(u), float(a)
            return abs(un - an) <= self.NUM_TOLERANCE
        except (TypeError, ValueError):
            return u == a

    @staticmethod
    def from_dict(data: dict) -> "CalculationQuestion":
        return CalculationQuestion(
            text=data.get("text", ""),
            answer=data.get("answer", ""),
            subject=data.get("subject", ""),
        )


# ==================== 工厂 ====================

class QuestionFactory:
    """题目工厂：注册六种题型；v1 别名 选择题 走 from_dict 分发"""

    _registry = {}

    @classmethod
    def register(cls, type_name: str, question_class: type):
        cls._registry[type_name] = question_class

    @classmethod
    def get_class(cls, type_name: str):
        return cls._registry.get(type_name)

    @classmethod
    def get_all_types(cls) -> list:
        return list(TYPE_ORDER)

    @classmethod
    def create_question(cls, q_type: str, **kwargs) -> Question:
        if q_type == "选择题":
            ct = kwargs.pop("choice_type", "single")
            kwargs.pop("multiple_answers", None)
            q_class = MultipleChoiceQuestion if str(ct).lower() == "multiple" else SingleChoiceQuestion
            return q_class(**kwargs)
        q_class = cls.get_class(q_type)
        if q_class is None:
            raise ValueError(f"未知题型: {q_type}")
        kwargs.pop("choice_type", None)
        kwargs.pop("multiple_answers", None)
        return q_class(**kwargs)


QuestionFactory.register("单选题", SingleChoiceQuestion)
QuestionFactory.register("多选题", MultipleChoiceQuestion)
QuestionFactory.register("判断题", TrueFalseQuestion)
QuestionFactory.register("填空题", FillBlankQuestion)
QuestionFactory.register("简答题", EssayQuestion)
QuestionFactory.register("计算题", CalculationQuestion)
QuestionFactory.register("选择题", ChoiceQuestion)  # v1 读取别名（from_dict 内分发）
