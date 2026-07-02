# backend/routers/hobby_router.py
"""취미 상세/카테고리 라우터 — /hobby_detail, /categories."""
from fastapi import APIRouter, Depends

from auth import verify_jwt
from dependencies import get_hobby_service
from schemas.hobby import DetailReq
from services.hobby_service import HobbyService

router = APIRouter()


@router.post("/hobby_detail")
def hobby_detail(req: DetailReq, user: dict = Depends(verify_jwt),
                 service: HobbyService = Depends(get_hobby_service)):
    return service.get_detail(user, req.hobby_id, req.meta)


@router.get("/categories")
def categories(service: HobbyService = Depends(get_hobby_service)):
    return {"categories": service.get_categories()}
