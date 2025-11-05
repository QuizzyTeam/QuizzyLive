from datetime import datetime, timezone
from typing import Any, Dict

from ..core.supabase_client import get_supabase
from ..repositories.quiz_session_repository import QuizSessionRepository


class QuizSessionService:
    """
    Сервіс для збереження завершених live-сесій у Supabase.
    """

    def __init__(self, repo: QuizSessionRepository | None = None) -> None:
        if repo is None:
            repo = QuizSessionRepository(get_supabase())
        self.repo = repo

    def save_finished_session(self, snapshot: Dict[str, Any]) -> None:
        """
        Приймає snapshot завершеної сесії (FinishedSessionSnapshot.model_dump())
        і зберігає його у таблицю quiz_sessions.
        """
        session_id = snapshot["sessionId"]
        room_code = snapshot["roomCode"]
        quiz_id = snapshot.get("quizId")

        created_at_ms = int(snapshot["createdAt"])
        ended_at_ms = int(snapshot["EndedAt"]) if "EndedAt" in snapshot else int(
            snapshot["endedAt"]
        )

        created_at = datetime.fromtimestamp(
            created_at_ms / 1000.0, tz=timezone.utc
        )
        ended_at = datetime.fromtimestamp(
            ended_at_ms / 1000.0, tz=timezone.utc
        )

        questions = snapshot["questions"]
        scoreboard = snapshot["scoreboard"]

        # ВАЖЛИВО: Supabase очікує JSON-серіалізовні значення,
        # тому datetime конвертуємо в ISO-строки.
        row = {
            "id": session_id,
            "room_code": room_code,
            "quiz_id": quiz_id,
            "created_at": created_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "questions": questions,
            "scoreboard": scoreboard,
        }

        self.repo.insert_session(row)
