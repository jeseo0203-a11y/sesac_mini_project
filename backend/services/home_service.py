# backend/services/home_service.py
"""HomeService — 홈 화면 응답 조립(데일리 추천, 무드, 카테고리, 보관함 개수 등).
Repository·다른 Service를 조합만 할 뿐 SQL이나 취미 랭킹 로직을 직접 갖지 않는다."""
from hobby_agents import CATEGORY_EMOJI, CATEGORY_LABEL, hobby_by_id, hobby_public

from repositories.mood_repository import MoodRepository
from repositories.saved_hobby_repository import SavedHobbyRepository
from services.conversation_service import ConversationService
from services.mood_service import MOODS


class HomeService:
    def __init__(self, mood_repo: MoodRepository, saved_hobby_repo: SavedHobbyRepository,
                conversation_service: ConversationService) -> None:
        self._mood_repo = mood_repo
        self._saved_hobby_repo = saved_hobby_repo
        self._conversation_service = conversation_service

    def get_home(self, user: dict) -> dict:
        sub = user["sub"]
        rep = self._conversation_service.get_last_report(sub)
        if rep and rep.get("items"):
            top_id = rep["items"][0]["id"]
            featured = hobby_public(hobby_by_id(top_id))
            featured["why"] = rep["items"][0].get("why", "")
        else:
            featured = hobby_public(hobby_by_id("plant"))
            featured["why"] = "가볍게 시작하기 좋은, 회복에 도움이 되는 취미예요."

        today_mood = self._mood_repo.get_today(sub)
        saved_count = self._saved_hobby_repo.count(sub)

        categories = [
            {"key": k, "label": v, "emoji": CATEGORY_EMOJI.get(k, "🎯")}
            for k, v in CATEGORY_LABEL.items()
        ]

        return {
            "name": user.get("name") or "친구",
            "picture": user.get("picture", ""),
            "moods": MOODS,
            "today_mood": today_mood,
            "featured": featured,
            "categories": categories,
            "has_report": bool(rep),
            "in_progress": self._conversation_service.has_active_session_key(sub),
            "saved_count": saved_count,
        }
