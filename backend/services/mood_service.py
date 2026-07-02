# backend/services/mood_service.py
"""MoodService — 홈 컨디션 칩(무드) 기록/조회 비즈니스 로직."""
from fastapi import HTTPException

from repositories.mood_repository import MoodRepository

# 무드 프리셋(홈 컨디션 칩) — 에너지 힌트를 프로필 축에 반영
MOODS = [
    {"key": "tired", "label": "지쳐요", "emoji": "😮‍💨", "energy": 0.12},
    {"key": "relaxed", "label": "편안해요", "emoji": "😌", "energy": 0.35},
    {"key": "curious", "label": "궁금해요", "emoji": "🤔", "energy": 0.6},
    {"key": "energetic", "label": "활기차요", "emoji": "⚡", "energy": 0.85},
]


class MoodService:
    def __init__(self, mood_repo: MoodRepository) -> None:
        self._mood_repo = mood_repo

    def set_mood(self, user_id: str, mood_key: str) -> dict:
        mood = next((m for m in MOODS if m["key"] == mood_key), None)
        if not mood:
            raise HTTPException(400, "알 수 없는 무드")
        self._mood_repo.add(user_id, mood["key"], mood["energy"])
        return mood

    def get_recent_moods(self, user_id: str) -> list[dict]:
        return self._mood_repo.get_recent(user_id, limit=30)
