# backend/schemas/library.py
"""보관함(저장한 취미) 관련 Request DTO."""
from typing import Optional

from pydantic import BaseModel


class SaveReq(BaseModel):
    hobby_id: str
    status: str = "관심 있음"
    meta: Optional[dict] = None  # 카탈로그 밖(커스텀) 취미 저장용 전체 메타


class StatusReq(BaseModel):
    hobby_id: str
    status: str
