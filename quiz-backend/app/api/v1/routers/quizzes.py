import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, status
from redis.asyncio import Redis
from typing import Annotated

from ....schemas.quiz_schemas import QuizCreateIn, QuizOut, QuizUpdateIn, QuizListItem
from ....services.quiz_service import QuizService
from ....repositories.quiz_repository import QuizRepository
from ....core.supabase_client import get_supabase
from ....core.redis_manager import get_redis
from ....services.room_quiz_cache import fetch_room_quiz, store_room_quiz

router = APIRouter(prefix="/quizzes", tags=["quizzes"])

# Dependency фабрика сервісу

def get_service() -> QuizService:
    repo = QuizRepository(get_supabase())
    return QuizService(repo)

ServiceDep = Annotated[QuizService, Depends(get_service)]

@router.get("/", response_model=list[QuizListItem])
async def list_quizzes(svc: ServiceDep):
    return svc.list_quizzes()

def _is_uuid_like(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(quiz_id: str, svc: ServiceDep, redis: Redis = Depends(get_redis)):
    data: dict | None = None

    if _is_uuid_like(quiz_id):
        data = svc.get_quiz(quiz_id)
    else:
        # 1) пробуємо знайти в Redis за roomCode
        data = await fetch_room_quiz(redis, quiz_id)

        # 2) fallback: якщо є лише meta, беремо справжній quiz_id і кешуємо
        if not data:
            meta_raw = await redis.get(f"quiz:session_meta:{quiz_id}")
            if meta_raw:
                meta = json.loads(meta_raw)
                original_id = meta.get("quizId")
                if original_id:
                    data = svc.get_quiz(original_id)
                    if data:
                        await store_room_quiz(redis, quiz_id, data)

    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return data

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_quiz(payload: QuizCreateIn, svc: ServiceDep):
    quiz_id = svc.create_quiz(
        payload.title,
        payload.description,          
        [q.model_dump() for q in payload.questions]
    )
    return {"id": quiz_id}


@router.put("/{quiz_id}")
async def update_quiz(quiz_id: str, payload: QuizUpdateIn, svc: ServiceDep):
    if payload.title is None and payload.description is None and payload.questions is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")

    if not svc.get_quiz(quiz_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    svc.update_quiz(
        quiz_id,
        payload.title,
        payload.description,    
        [q.model_dump() for q in payload.questions] if payload.questions is not None else None,
    )
    return {"status": "ok"}


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(quiz_id: str, svc: ServiceDep):
    # Ідемпотентність: не розкривати існування — але дамо 404 для чіткості фронту
    if not svc.get_quiz(quiz_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    svc.delete_quiz(quiz_id)
    return None