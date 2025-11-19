from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from redis.asyncio import Redis
import json
import uuid

from app.core.grpc_client import grpc_client
from app.core.redis_manager import get_redis
from app.services.quiz_service import QuizService
from app.repositories.quiz_repository import QuizRepository
from app.core.supabase_client import get_supabase
from app.services.room_quiz_cache import store_room_quiz, ROOM_CACHE_TTL

router = APIRouter(prefix="/sessions", tags=["sessions"])

class CreateSessionRequest(BaseModel):
    quizId: str

class CreateSessionResponse(BaseModel):
    roomCode: str
    hostToken: str

SESSION_META_TTL = ROOM_CACHE_TTL


@router.post("/", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: CreateSessionRequest, r: Redis = Depends(get_redis)):
    # 1. Отримуємо дані про квіз (нам потрібна назва для Lobby)
    repo = QuizRepository(get_supabase())
    svc = QuizService(repo)
    quiz = svc.get_quiz(payload.quizId)
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    # 2. Генеруємо унікальний код
    room_code = grpc_client.get_new_room_code(length=5)
    if await r.exists(f"quiz:room:{room_code}:state"):
        room_code = grpc_client.get_new_room_code(length=6)

    host_token = str(uuid.uuid4())

    # 3. Зберігаємо метадані в Redis (включаючи TITLE)
    # Тепер фронтенду не треба робити зайвий запит до Postgres
    session_meta = {
        "quizId": payload.quizId,
        "quizTitle": quiz["title"],  # <--- Зберігаємо назву
        "hostToken": host_token,
        "status": "CREATED"
    }
    
    await r.setex(f"quiz:session_meta:{room_code}", SESSION_META_TTL, json.dumps(session_meta))

    # 4. Кешуємо повний квіз (разом із питаннями) для звернень через roomCode
    await store_room_quiz(r, room_code, quiz)

    return {"roomCode": room_code, "hostToken": host_token}

@router.get("/{room_code}/info")
async def get_session_info(room_code: str, r: Redis = Depends(get_redis)):
    # Сценарій 1: Сесія активна (дані в повноцінному ключі session:XXX)
    session_raw = await r.get(f"session:{room_code}")
    if session_raw:
        session_data = json.loads(session_raw)
        
        # Назву квіза треба дістати. Якщо вона є в session_data - супер,
        # якщо ні (старі сесії) - спробуємо знайти в метаданих або залишимо дефолт.
        quiz_title = session_data.get("quizTitle")
        if not quiz_title:
             # Fallback: спроба читати з метаданих, якщо вони ще живі
             meta_raw = await r.get(f"quiz:session_meta:{room_code}")
             if meta_raw:
                 quiz_title = json.loads(meta_raw).get("quizTitle")
        
        state_raw = await r.get(f"quiz:room:{room_code}:state")
        status_val = "UNKNOWN"
        if state_raw:
            status_val = json.loads(state_raw).get("phase", "UNKNOWN")
            
        return {
            "roomCode": room_code,
            "quizId": session_data.get("quizId"),
            "quizTitle": quiz_title or "Quiz",
            "status": status_val
        }

    # Сценарій 2: Сесія тільки створена (метадані)
    meta_raw = await r.get(f"quiz:session_meta:{room_code}")
    if meta_raw:
        meta = json.loads(meta_raw)
        return {
            "roomCode": room_code,
            "quizId": meta["quizId"],
            "quizTitle": meta.get("quizTitle", "Loading..."),
            "status": "CREATED"
        }
        
    raise HTTPException(status_code=404, detail="Session not found")