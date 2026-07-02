# backend/schemas/hobby.py
"""취미 상세 조회 관련 Request DTO."""
from typing import Optional

from pydantic import BaseModel


class DetailReq(BaseModel):
    hobby_id: str
    meta: Optional[dict] = None
