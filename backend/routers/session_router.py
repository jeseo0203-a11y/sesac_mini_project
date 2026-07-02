# backend/routers/session_router.py
"""세션(대화) 라우터 — /session, /message, /feedback.
Controller 계층: 요청 파싱과 인증(Depends) 연결만 담당하고, 실제 로직은 ConversationService에 위임한다."""
from fastapi import APIRouter, Depends

from auth import verify_jwt
from dependencies import get_conversation_service
from schemas.conversation import FbReq, MsgReq, StartReq
from services.conversation_service import ConversationService

router = APIRouter()


@router.post("/session")
def start_session(_: StartReq = StartReq(), user: dict = Depends(verify_jwt),
                  service: ConversationService = Depends(get_conversation_service)):
    return service.start_session(user["sub"])


@router.post("/message")
def message(req: MsgReq, user: dict = Depends(verify_jwt),
           service: ConversationService = Depends(get_conversation_service)):
    out = service.send_message(user["sub"], req.session_id, req.text,
                               req.choice_index, req.choice_indices, req.n_options)
    return {"message": out}


@router.post("/feedback")
def feedback(req: FbReq, user: dict = Depends(verify_jwt),
            service: ConversationService = Depends(get_conversation_service)):
    out = service.submit_feedback(user["sub"], req.session_id, req.hobby_id,
                                  req.kind, req.reason)
    return {"message": out}
