# backend/routers/library_router.py
"""보관함 라우터 — /save, /library."""
from fastapi import APIRouter, Depends

from auth import verify_jwt
from dependencies import get_library_service
from schemas.library import SaveReq, StatusReq
from services.library_service import LibraryService

router = APIRouter()


@router.post("/save")
def save_hobby(req: SaveReq, user: dict = Depends(verify_jwt),
              service: LibraryService = Depends(get_library_service)):
    service.save(user["sub"], req.hobby_id, req.status, req.meta)
    return {"ok": True}


@router.get("/library")
def library(user: dict = Depends(verify_jwt),
           service: LibraryService = Depends(get_library_service)):
    return {"items": service.list_saved(user["sub"])}


@router.patch("/library")
def update_status(req: StatusReq, user: dict = Depends(verify_jwt),
                  service: LibraryService = Depends(get_library_service)):
    service.update_status(user["sub"], req.hobby_id, req.status)
    return {"ok": True}


@router.delete("/library/{hobby_id}")
def remove_saved(hobby_id: str, user: dict = Depends(verify_jwt),
                 service: LibraryService = Depends(get_library_service)):
    service.remove(user["sub"], hobby_id)
    return {"ok": True}
