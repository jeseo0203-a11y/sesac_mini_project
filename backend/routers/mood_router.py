# backend/routers/mood_router.py
"""무드 라우터 — /mood, /moods."""
from fastapi import APIRouter, Depends

from auth import verify_jwt
from dependencies import get_mood_service
from schemas.mood import MoodReq
from services.mood_service import MoodService

router = APIRouter()


@router.post("/mood")
def set_mood(req: MoodReq, user: dict = Depends(verify_jwt),
            service: MoodService = Depends(get_mood_service)):
    mood = service.set_mood(user["sub"], req.mood)
    return {"ok": True, "mood": mood}


@router.get("/moods")
def get_moods(user: dict = Depends(verify_jwt),
             service: MoodService = Depends(get_mood_service)):
    return {"moods": service.get_recent_moods(user["sub"])}
