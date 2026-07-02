# backend/schemas/mood.py
"""무드(홈 컨디션 칩) 관련 Request DTO."""
from pydantic import BaseModel


class MoodReq(BaseModel):
    mood: str
