# backend/repositories/mood_repository.py
"""MoodRepository — moods 테이블 전용 데이터 접근 계층(PostgreSQL)."""
from typing import Optional

from db.connection import get_cursor


class MoodRepository:
    def add(self, user: str, mood_key: str, energy: float) -> None:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO moods(user_email, mood, energy) VALUES (%s, %s, %s)",
                (user, mood_key, energy),
            )

    def get_today(self, user: str) -> Optional[str]:
        """오늘(DB 서버 기준 날짜) 기록된 가장 최근 무드 키를 반환. 없으면 None."""
        with get_cursor() as cur:
            cur.execute(
                "SELECT mood FROM moods WHERE user_email=%s AND created_at::date = now()::date "
                "ORDER BY id DESC LIMIT 1",
                (user,),
            )
            row = cur.fetchone()
        return row["mood"] if row else None

    def get_recent(self, user: str, limit: int = 30) -> list[dict]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT mood, energy, created_at FROM moods WHERE user_email=%s "
                "ORDER BY id DESC LIMIT %s",
                (user, limit),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]
