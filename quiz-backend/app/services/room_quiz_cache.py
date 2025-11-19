import json
from typing import Any, Dict, List

from redis.asyncio import Redis

ROOM_CACHE_TTL = 6 * 60 * 60  # 6 hours


def _room_quiz_key(room_code: str) -> str:
    return f"quiz:room:{room_code}:quiz"


async def store_room_quiz(r: Redis, room_code: str, quiz_payload: Dict[str, Any]) -> None:
    """
    Persist the full quiz payload (QuizOut shape) for a specific room code.
    """
    if not quiz_payload:
        return
    await r.setex(_room_quiz_key(room_code), ROOM_CACHE_TTL, json.dumps(quiz_payload))


async def fetch_room_quiz(r: Redis, room_code: str) -> Dict[str, Any] | None:
    raw = await r.get(_room_quiz_key(room_code))
    if not raw:
        return None
    return json.loads(raw)


async def delete_room_quiz(r: Redis, room_code: str) -> None:
    await r.delete(_room_quiz_key(room_code))


def questions_to_runtime(quiz_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert QuizOut.questions (camelCase) into runtime format (snake_case)
    expected by the WebSocket game loop.
    """
    runtime_questions: List[Dict[str, Any]] = []
    for item in quiz_payload.get("questions", []):
        runtime_questions.append(
            {
                "id": item.get("id"),
                "question_text": item.get("questionText"),
                "answers": item.get("answers", []),
                "correct_answer": item.get("correctAnswer"),
                "position": item.get("position"),
            }
        )
    return runtime_questions

