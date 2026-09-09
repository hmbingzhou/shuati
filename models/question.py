"""
题目模型模块
使用策略模式 + 工厂模式，预留题型扩展接口
"""

from abc import ABC, abstractmethod
from utils.helpers import yellow


class Question(ABC):
    """题目抽象基类"""

    def __init__(self, text: str, answer: str, subject: str = ""):
        self.text = text
        self.answer = answer.strip()
        self.subject = subject
        self.flag_star = False   # 网页版标记：黄色星星
        self.flag_cross = False  # 网页版标记：红色叉

    @abstractmethod
    def get_type_name(self) -> str:
        """返回题型名称"""
        pass

    @abstractmethod
    def get_type_label(self) -> str:
        """返回题型标签（用于显示，如单选题/多选题/判断题/填空题）"""
        pass

    @abstractmethod
    def display(self) -> str:
        """返回题目的显示文本"""
        pass

    @abstractmethod
    def check_answer(self, user_answer: str) -> bool:
        """判断用户答案是否正确"""
        pass

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "type": self.get_type_name(),
            "text": self.text,
            "answer": self.answer,
            "subject": self.subject,
            "flag_star": bool(self.flag_star),
            "flag_cross": bool(self.flag_cross),
        }

    @staticmethod
    def from_dict(data: dict) -> "Question":
        """从字典反序列化"""
        q_type = data["type"]
        q_class = QuestionFactory.get_class(q_type)
        if q_class is None:
            raise ValueError(f"未知题型: {q_type}")
        # 子类特有的参数由各自工厂方法处理
        q = q_class.from_dict(data)
        # 标记字段（旧数据无这两个字段时为 False）
        q.flag_star = bool(data.get("flag_star", False))
        q.flag_cross = bool(data.get("flag_cross", False))
        return q


class ChoiceQuestion(Question):
    """选择题（单选题/多选题共用）"""

    def __init__(self, text: str, options: list, answer: str,
                 subject: str = "", choice_type: str = "single",
                 multiple_answers: list = None):
        super().__init__(text, answer, subject)
        self.options = options  # [("A", "选项文本"), ("B", "选项文本"), ...]
        self.choice_type = choice_type  # "single" 或 "multiple"
        self.multiple_answers = multiple_answers  # 多选题的标准答案列表，如 ["A", "B", "D"]

    def get_type_name(self) -> str:
        return "选择题"

    def get_type_label(self) -> str:
        """返回题型标签，用于显示"""
        if self.choice_type == "multiple":
            return "多选题"
        return "单选题"

    def display(self) -> str:
        label = self.get_type_label()
        lines = [f"{yellow(f'[{label}]')} {self.text}"]
        for label_opt, option_text in self.options:
            lines.append(f"  {label_opt}. {option_text}")
        return "\n".join(lines)

    def check_answer(self, user_answer: str) -> bool:
        if self.choice_type == "multiple":
            # 多选题：用户输入 "A B D" 或 "ABD" 或 "a b d"，与标准答案集合比对
            user_set = set(user_answer.strip().upper().replace(" ", ""))
            correct_set = set(self.answer.strip().upper().replace(" ", ""))
            # 检查用户答案是否包含无效选项
            valid_labels = {opt[0] for opt in self.options}
            if not user_set.issubset(valid_labels):
                return False
            return user_set == correct_set
        else:
            # 单选题：直接比较
            return user_answer.strip().upper() == self.answer.strip().upper()

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["options"] = self.options
        d["choice_type"] = self.choice_type
        d["multiple_answers"] = self.multiple_answers
        return d

    @staticmethod
    def from_dict(data: dict) -> "ChoiceQuestion":
        # 兼容旧数据：没有 choice_type 字段时，默认识别为单选题
        choice_type = data.get("choice_type", "single")
        if choice_type == "single" and "choice_type" not in data:
            print("  [提示] 已自动将旧选择题识别为单选题")
        multiple_answers = data.get("multiple_answers", None)
        return ChoiceQuestion(
            text=data["text"],
            options=data["options"],
            answer=data["answer"],
            subject=data.get("subject", ""),
            choice_type=choice_type,
            multiple_answers=multiple_answers,
        )


class TrueFalseQuestion(Question):
    """判断题"""

    # 答案映射表（不区分大小写），统一存储为"正确"/"错误"
    TF_MAP = {
        "对": "正确", "正确": "正确", "t": "正确", "true": "正确", "√": "正确", "v": "正确",
        "错": "错误", "错误": "错误", "f": "错误", "false": "错误", "×": "错误", "x": "错误",
    }

    def __init__(self, text: str, answer: str, subject: str = ""):
        # 统一存储为"正确"/"错误"，确保与旧数据兼容
        normalized = self._normalize(answer.strip())
        super().__init__(text, normalized, subject)

    @staticmethod
    def _normalize(val: str) -> str:
        """将多种答案格式统一为标准值"""
        return TrueFalseQuestion.TF_MAP.get(val.lower(), val)

    def get_type_name(self) -> str:
        return "判断题"

    def get_type_label(self) -> str:
        return "判断题"

    def display(self) -> str:
        return f"{yellow('[判断题]')} {self.text}\n  请输入：正确/错误 / 对/错 / t/f / true/false"

    def check_answer(self, user_answer: str) -> bool:
        return self._normalize(user_answer.strip()) == self.answer

    @staticmethod
    def from_dict(data: dict) -> "TrueFalseQuestion":
        return TrueFalseQuestion(
            text=data["text"],
            answer=data["answer"],
            subject=data.get("subject", ""),
        )


class FillBlankQuestion(Question):
    """填空题"""

    def get_type_name(self) -> str:
        return "填空题"

    def get_type_label(self) -> str:
        return "填空题"

    def display(self) -> str:
        return f"{yellow('[填空题]')} {self.text}"

    def check_answer(self, user_answer: str) -> bool:
        return user_answer.strip() == self.answer.strip()

    @staticmethod
    def from_dict(data: dict) -> "FillBlankQuestion":
        return FillBlankQuestion(
            text=data["text"],
            answer=data["answer"],
            subject=data.get("subject", ""),
        )


# ==================== 预留扩展：简答题示例 ====================
class EssayQuestion(Question):
    """简答题（扩展预留）"""

    def get_type_name(self) -> str:
        return "简答题"

    def get_type_label(self) -> str:
        return "简答题"

    def display(self) -> str:
        return f"{yellow('[简答题]')} {self.text}"

    def check_answer(self, user_answer: str) -> bool:
        # 简答题可采用关键字匹配或人工判断，此处简单实现为完全匹配或含有关键词
        # 预留：可扩展为 AI 评分或关键词匹配
        return user_answer.strip() == self.answer.strip()

    @staticmethod
    def from_dict(data: dict) -> "EssayQuestion":
        return EssayQuestion(
            text=data["text"],
            answer=data["answer"],
            subject=data.get("subject", ""),
        )


# ==================== 工厂模式 ====================

class QuestionFactory:
    """题目工厂 - 注册机制，新增题型只需在此注册"""

    _registry = {}  # type_name -> (class, from_dict_method)

    @classmethod
    def register(cls, type_name: str, question_class: type):
        """注册题型"""
        cls._registry[type_name] = question_class

    @classmethod
    def get_class(cls, type_name: str):
        """获取题型类"""
        return cls._registry.get(type_name)

    @classmethod
    def get_all_types(cls) -> list:
        """获取所有已注册的题型名称"""
        return list(cls._registry.keys())

    @classmethod
    def create_question(cls, q_type: str, **kwargs) -> Question:
        """工厂方法创建题目"""
        q_class = cls.get_class(q_type)
        if q_class is None:
            raise ValueError(f"未知题型: {q_type}")
        return q_class(**kwargs)


# 注册已知题型
QuestionFactory.register("判断题", TrueFalseQuestion)
QuestionFactory.register("选择题", ChoiceQuestion)
QuestionFactory.register("填空题", FillBlankQuestion)
QuestionFactory.register("简答题", EssayQuestion)  # 预留扩展
