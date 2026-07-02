# backend/repositories/hobby_report_repository.py
"""HobbyReportRepository — hobby_reports 테이블(완료된 취미 DNA 리포트 기록) 전용 데이터 접근 계층."""
from typing import Optional

from psycopg2.extras import Json

from db.connection import get_cursor


class HobbyReportRepository:
    def save(self, user: str, report: dict) -> None:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO hobby_reports(user_email, report) VALUES (%s, %s)",
                (user, Json(report)),
            )

    def get_latest(self, user: str) -> Optional[dict]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT report FROM hobby_reports WHERE user_email=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (user,),
            )
            row = cur.fetchone()
        return row["report"] if row else None
