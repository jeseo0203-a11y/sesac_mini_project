# backend/routers/home_router.py
"""홈 화면 라우터 — /home."""
from fastapi import APIRouter, Depends

from auth import verify_jwt
from dependencies import get_home_service
from services.home_service import HomeService

router = APIRouter()


@router.get("/home")
def home(user: dict = Depends(verify_jwt),
        service: HomeService = Depends(get_home_service)):
    return service.get_home(user)
