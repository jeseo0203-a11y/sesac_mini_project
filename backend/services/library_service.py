# backend/services/library_service.py
"""LibraryService — 보관함(저장한 취미) 저장/조회/상태변경/삭제 비즈니스 로직."""
from typing import Optional

from fastapi import HTTPException

from hobby_agents import hobby_by_id, hobby_public

from repositories.saved_hobby_repository import SavedHobbyRepository


class LibraryService:
    def __init__(self, saved_hobby_repo: SavedHobbyRepository) -> None:
        self._repo = saved_hobby_repo

    def save(self, user_id: str, hobby_id: str, status: str, client_meta: Optional[dict]) -> None:
        # 카탈로그에 있으면 서버 메타, 없으면(커스텀) 클라이언트가 보낸 meta 사용
        h = hobby_by_id(hobby_id)
        meta = hobby_public(h) if h else client_meta
        if not meta:
            raise HTTPException(404, "취미 정보를 찾을 수 없어요(meta 필요)")
        self._repo.upsert(user_id, hobby_id, status, meta)

    def list_saved(self, user_id: str) -> list[dict]:
        rows = self._repo.list_by_user(user_id)
        items = []
        for r in rows:
            # meta는 JSONB 컬럼이라 psycopg2가 이미 dict로 역직렬화해 돌려준다.
            it = r["meta"]
            if it is None:
                h = hobby_by_id(r["hobby_id"])
                if not h:
                    continue
                it = hobby_public(h)
            it["id"] = r["hobby_id"]
            it["status"] = r["status"]
            it["saved_at"] = r["saved_at"].strftime("%Y.%m.%d")
            items.append(it)
        return items

    def update_status(self, user_id: str, hobby_id: str, status: str) -> None:
        updated = self._repo.update_status(user_id, hobby_id, status)
        if not updated:
            raise HTTPException(404, "보관함에 없는 취미")

    def remove(self, user_id: str, hobby_id: str) -> None:
        self._repo.delete(user_id, hobby_id)
