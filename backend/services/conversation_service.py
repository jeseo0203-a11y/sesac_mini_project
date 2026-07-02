# backend/services/conversation_service.py
"""ConversationService — 취미 발굴 대화 세션의 비즈니스 로직.
세션 생성/메시지 처리/피드백 처리를 담당하며, 세션·최신 리포트·전역 자기개선 랭커의
상태를 이 서비스 안에 캡슐화한다.
(MVP: 인메모리·단일 프로세스 근사. 실서비스 전환 시 세션은 Redis, 랭커 학습치는 DB 집계로 옮긴다.)
"""
import uuid
from typing import Optional

from fastapi import HTTPException

from hobby_agents import HybridConversationAgent, SelfImprovingRanker

from repositories.hobby_report_repository import HobbyReportRepository

GREETING = (
    "안녕하세요, 하비DNA예요. 오늘 당신의 마음을 진단해 딱 맞는 취미를 찾아드릴게요. "
    "요즘 마음이나 일상은 어떤가요? 편하게 한두 문장 들려주세요."
)


class ConversationService:
    def __init__(self, hobby_report_repo: HobbyReportRepository) -> None:
        self._ranker = SelfImprovingRanker()
        self._sessions: dict[str, HybridConversationAgent] = {}
        self._last_report: dict[str, dict] = {}
        self._hobby_report_repo = hobby_report_repo

    def start_session(self, user_id: str) -> dict:
        sid = uuid.uuid4().hex
        self._sessions[sid] = HybridConversationAgent(user_id=user_id, ranker=self._ranker)
        return {"session_id": sid, "message": {"type": "say", "text": GREETING}}

    def _get_agent(self, session_id: str) -> HybridConversationAgent:
        agent = self._sessions.get(session_id)
        if not agent:
            raise HTTPException(404, "세션이 없어요. 새로고침 후 다시 시작해 주세요.")
        return agent

    def send_message(self, user_id: str, session_id: str, text: str,
                     choice_index: Optional[int], choice_indices: Optional[list[int]],
                     n_options: Optional[int]) -> dict:
        agent = self._get_agent(session_id)
        out = agent.send(text, choice_index=choice_index,
                         choice_indices=choice_indices, n_options=n_options)
        if out.get("type") == "report":
            report = out.get("report", {})
            self._last_report[user_id] = report
            self._hobby_report_repo.save(user_id, report)
        return out

    def submit_feedback(self, user_id: str, session_id: str, hobby_id: str,
                        kind: str, reason: Optional[str]) -> dict:
        agent = self._get_agent(session_id)
        out = agent.feedback(hobby_id, kind, reason)
        if out.get("type") == "report":
            report = out.get("report", {})
            self._last_report[user_id] = report
            self._hobby_report_repo.save(user_id, report)
        return out

    def get_last_report(self, user_id: str) -> Optional[dict]:
        return self._last_report.get(user_id)

    def has_active_session_key(self, key: str) -> bool:
        """원본 코드의 `sub in SESSIONS` 동작을 그대로 보존한 메서드.
        주의: SESSIONS는 session_id(uuid)를 키로 쓰므로 user_id로 조회하면 사실상 항상 False다.
        (원본에 있던 기존 동작이라 이번 리팩터링 범위에서는 그대로 옮기고, 별도로 알려드린다.)"""
        return key in self._sessions
