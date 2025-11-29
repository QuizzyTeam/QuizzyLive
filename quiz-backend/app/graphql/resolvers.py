from typing import Optional
import strawberry

from ..repositories.quiz_repository import QuizRepository
from ..services.quiz_service import QuizService
from .types import QuizInfoType

# -------------------------------
# Helper
# -------------------------------

def get_quiz_service() -> QuizService:
    """
    Фабрика сервісу для резолвера.
    """
    from app.core.supabase_client import get_supabase
    repo = QuizRepository(get_supabase())
    return QuizService(repo=repo)

# -------------------------------
# Query Resolver
# -------------------------------

async def resolve_quiz_info(
    root: None,
    info: strawberry.types.Info,
    id: str
) -> Optional[QuizInfoType]:
    """
    Повертає інформацію про вікторину для модалки.
    """
    quiz_service = get_quiz_service()
    data = quiz_service.get_quiz(id)
    if not data:
        return None

    return QuizInfoType(
        id=data["id"],
        title=data["title"],
        description=data.get("description", ""),
        createdAt=data.get("createdAt", ""),
        updatedAt=data.get("updatedAt", ""),
        questionCount=data.get("questionCount", 0),
        rating=data.get("rating", 0),
    )
