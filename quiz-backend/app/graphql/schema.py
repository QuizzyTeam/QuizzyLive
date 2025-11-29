# app/graphql/schema.py
import strawberry
from typing import Optional, List

from .types import QuizShort, QuizFull
from .resolvers import (
    resolve_quiz,
    resolve_quiz_info,
    resolve_quizzes,
    resolve_create_quiz,
    resolve_delete_quiz,
)

@strawberry.type
class Query:
    quizzes: List[QuizShort] = strawberry.field(resolver=resolve_quizzes)

    quiz: Optional[QuizFull] = strawberry.field(
        resolver=resolve_quiz,
        description="Get quiz with questions"
    )

    quizInfo: Optional[QuizFull] = strawberry.field(
        resolver=resolve_quiz_info,
        description="Get quiz info (title, dates, questionCount, description, rating)"
    )

@strawberry.type
class Mutation:
    createQuiz: str = strawberry.field(resolver=resolve_create_quiz)
    deleteQuiz: bool = strawberry.field(resolver=resolve_delete_quiz)

schema = strawberry.Schema(query=Query, mutation=Mutation)
