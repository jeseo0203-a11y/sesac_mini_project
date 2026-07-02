# backend/dependencies.py
"""DI 컴포지션 루트 — Repository/Service 싱글턴을 조립해 라우터에 주입한다.
FastAPI Depends로 연결하므로 테스트 시 app.dependency_overrides로 목(mock) 교체가 쉽다.
(lru_cache로 인자 없는 팩토리를 감싸 프로세스당 1개 인스턴스만 만든다 — 기존 main.py의
전역 변수 방식과 동일한 싱글턴 수명을 유지하면서 명시적인 DI 지점으로 옮긴 것.)
"""
from functools import lru_cache

from hobby_agents import GPTBackend

from repositories.hobby_report_repository import HobbyReportRepository
from repositories.mood_repository import MoodRepository
from repositories.saved_hobby_repository import SavedHobbyRepository
from repositories.user_repository import UserRepository
from services.conversation_service import ConversationService
from services.hobby_service import HobbyService
from services.home_service import HomeService
from services.library_service import LibraryService
from services.mood_service import MoodService


@lru_cache
def get_mood_repository() -> MoodRepository:
    return MoodRepository()


@lru_cache
def get_saved_hobby_repository() -> SavedHobbyRepository:
    return SavedHobbyRepository()


@lru_cache
def get_user_repository() -> UserRepository:
    return UserRepository()


@lru_cache
def get_hobby_report_repository() -> HobbyReportRepository:
    return HobbyReportRepository()


@lru_cache
def get_gpt_backend() -> GPTBackend:
    return GPTBackend()


@lru_cache
def get_conversation_service() -> ConversationService:
    return ConversationService(get_hobby_report_repository())


@lru_cache
def get_mood_service() -> MoodService:
    return MoodService(get_mood_repository())


@lru_cache
def get_home_service() -> HomeService:
    return HomeService(get_mood_repository(), get_saved_hobby_repository(),
                       get_conversation_service())


@lru_cache
def get_hobby_service() -> HobbyService:
    return HobbyService(get_gpt_backend(), get_conversation_service())


@lru_cache
def get_library_service() -> LibraryService:
    return LibraryService(get_saved_hobby_repository())
