"""
错题本记录模型
"""

import datetime


class WrongRecord:
    """错题本条目"""

    def __init__(
        self,
        subject: str,
        question_text: str,
        question_type: str,
        correct_answer: str,
        wrong_answer: str,
        timestamp: str = None,
    ):
        self.subject = subject
        self.question_text = question_text
        self.question_type = question_type
        self.correct_answer = correct_answer
        self.wrong_answer = wrong_answer
        self.timestamp = timestamp or datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "correct_answer": self.correct_answer,
            "wrong_answer": self.wrong_answer,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict) -> "WrongRecord":
        return WrongRecord(
            subject=data["subject"],
            question_text=data["question_text"],
            question_type=data["question_type"],
            correct_answer=data["correct_answer"],
            wrong_answer=data["wrong_answer"],
            timestamp=data.get("timestamp", ""),
        )
