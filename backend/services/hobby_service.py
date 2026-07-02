# backend/services/hobby_service.py
"""HobbyService — 취미 상세 설명(개인화 포함) 및 카테고리 목록 조회 비즈니스 로직."""
from typing import Optional

from fastapi import HTTPException

from hobby_agents import (
    CATEGORY_EMOJI, CATEGORY_LABEL, GPTBackend, HOBBY_CATALOG, HOBBY_CATEGORY,
    explain_hobby, hobby_by_id, hobby_public,
)

from services.conversation_service import ConversationService


class HobbyService:
    def __init__(self, gpt: GPTBackend, conversation_service: ConversationService) -> None:
        self._gpt = gpt
        self._conversation_service = conversation_service

    def get_detail(self, user: dict, hobby_id: str, client_meta: Optional[dict]) -> dict:
        # 취미 메타 해석: 카탈로그 → 클라 meta → 최신 리포트 아이템
        h = hobby_by_id(hobby_id)
        meta = hobby_public(h) if h else client_meta
        if not meta:
            rep = self._conversation_service.get_last_report(user["sub"])
            if rep:
                meta = next((it for it in rep.get("items", []) if it.get("id") == hobby_id), None)
        if not meta:
            raise HTTPException(404, "취미 정보를 찾을 수 없어요")

        # 사용자 성향(있으면 개인화)
        rep = self._conversation_service.get_last_report(user["sub"])
        axis = (rep.get("profile", {}) or {}).get("axis") if rep else None
        detail = explain_hobby(meta, axis, self._gpt)
        return {"hobby": meta, "detail": detail, "personalized": bool(axis)}

    def get_categories(self) -> list[dict]:
        out = []
        for key, label in CATEGORY_LABEL.items():
            items = [hobby_public(h) for h in HOBBY_CATALOG if HOBBY_CATEGORY.get(h.id) == key]
            out.append({"key": key, "label": label, "emoji": CATEGORY_EMOJI.get(key, "🎯"),
                        "items": items})
        return out
