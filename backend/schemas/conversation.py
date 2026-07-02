# backend/schemas/conversation.py
"""대화(세션 시작/메시지/피드백) 관련 Request DTO."""
from typing import Optional

from pydantic import BaseModel


class StartReq(BaseModel):
    pass


class MsgReq(BaseModel):
    session_id: str
    text: str = ""
    choice_index: Optional[int] = None
    choice_indices: Optional[list[int]] = None
    n_options: Optional[int] = None


class FbReq(BaseModel):
    session_id: str
    hobby_id: str
    kind: str
    reason: Optional[str] = None
