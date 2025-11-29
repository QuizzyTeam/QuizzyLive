# app/graphql/resolvers.py
from typing import Optional, List

import strawberry

from ..repositories.quiz_repository import QuizRepository
from ..services.quiz_service import QuizService
from .types import QuizType, QuizInfoType, QuestionType


# -------------------------------
# Helpers
# -------------------------------

def get_quiz_service() -> QuizService:
    from app.core.supabase_client import get_supabase
    repo = QuizRepository(get_supabase())
    return QuizService(repo=repo)


# -------------------------------
# Query Resolvers
# -------------------------------

async def resolve_quiz_info(id: str) -> Optional[QuizInfoType]:
    quiz_service = get_quiz_service()

    data = quiz_service.get_quiz(id)
    if not data:
        return None

    return QuizInfoType(
        id=data["id"],
        title=data["title"],
        description=data.get("description", ""),
        createdAt=data["createdAt"],
        updatedAt=data["updatedAt"],
        questionCount=data.get("questionCount", 0),
        rating=data.get("rating", 0),
    )


async def resolve_quiz(id: str) -> Optional[QuizType]:
    quiz_service = get_quiz_service()

    data = quiz_service.get_quiz(id)
    if not data:
        return None

    questions = [
        QuestionType(
            id=q["id"],
            questionText=q["questionText"],
            answers=q["answers"],
            correctAnswer=q["correctAnswer"],
            position=q["position"],
        )
        for q in data.get("questions", [])
    ]

    return QuizType(
        id=data["id"],
        title=data["title"],
        description=data.get("description", ""),
        createdAt=data["createdAt"],
        updatedAt=data["updatedAt"],
        questionCount=data.get("questionCount", 0),
        rating=data.get("rating", 0),
        questions=questions,
    )


async def resolve_quizzes() -> List[QuizInfoType]:
    quiz_service = get_quiz_service()

    items = quiz_service.list_quizzes()
    result = []

    for i in items:
        result.append(
            QuizInfoType(
                id=i["id"],
                title=i["title"],
                description=i.get("description", ""),
                createdAt=i.get("createdAt", ""),
                updatedAt=i.get("updatedAt", ""),
                questionCount=i.get("questionCount", 0),
                rating=i.get("rating", 0),
            )
        )

    return result


# -------------------------------
# Mutations
# -------------------------------

@strawberry.input
class QuestionInput:
    questionText: str
    answers: List[str]
    correctAnswer: int


@strawberry.input
class QuizInput:
    title: str
    description: str
    questions: List[QuestionInput]


async def resolve_create_quiz(payload: QuizInput) -> str:
    quiz_service = get_quiz_service()

    questions = [
        {
            "questionText": q.questionText,
            "answers": q.answers,
            "correctAnswer": q.correctAnswer,
        }
        for q in payload.questions
    ]

    quiz_id = quiz_service.create_quiz(
        title=payload.title,
        description=payload.description,
        questions=questions,
    )

    return quiz_id


async def resolve_delete_quiz(id: str) -> bool:
    quiz_service = get_quiz_service()
    quiz_service.delete_quiz(id)
    return True
