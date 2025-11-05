from typing import Any, Dict

from supabase import Client


class QuizSessionRepository:
    def __init__(self, client: Client) -> None:
        self.client = client

    def insert_session(self, row: Dict[str, Any]) -> None:
        """
        Зберігає завершену live-сесію у таблицю quiz_sessions.

        Очікується, що row вже містить усі необхідні поля,
        які напряму відповідають колонкам таблиці.
        """
        self.client.table("quiz_sessions").insert(row).execute()
