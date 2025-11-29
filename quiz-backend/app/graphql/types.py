# app/graphql/types.py
import strawberry
from typing import List, Optional

@strawberry.type
class QuestionType:
    id: str
    questionText: str
    answers: List[str]
    correctAnswer: int
    position: int

@strawberry.type
class QuizInfoType:
    """
    Тип, який повертає всю інформацію про вікторину для інфо-екрану.
    """
    id: str
    title: str
    description: str
    createdAt: str
    updatedAt: str
    questionCount: int
    rating: int

@strawberry.type
class QuizType:
    # повний об'єкт з питаннями (якщо потрібно)
    id: str
    title: str
    description: str
    createdAt: str
    updatedAt: str
    questionCount: int
    rating: int
    questions: List[QuestionType]


@strawberry.type
class QuizShort:
    id: str
    title: str
    questionCount: int
    rating: int


@strawberry.type
class QuizFull:
    id: str
    title: str
    description: str
    createdAt: str
    updatedAt: str
    questionCount: int
    rating: int