import strawberry
from typing import Optional

from .types import QuizInfoType
from .resolvers import resolve_quiz_info

@strawberry.type
class Query:
    """
    Query для інформації про вікторину (інфо-модалка).
    """
    quizInfo: Optional[QuizInfoType] = strawberry.field(
        resolver=resolve_quiz_info,
        description="Отримати інформацію про вікторину для модалки"
    )

schema = strawberry.Schema(query=Query)
