# backend/repositories/saved_hobby_repository.py
"""SavedHobbyRepository — saved_hobbies 테이블(보관함) 전용 데이터 접근 계층(PostgreSQL).
meta는 JSONB 컬럼이라 psycopg2가 dict ↔ JSON을 자동 변환한다(별도 json.dumps/loads 불필요)."""
from psycopg2.extras import Json

from db.connection import get_cursor


class SavedHobbyRepository:
    def upsert(self, user: str, hobby_id: str, status: str, meta: dict) -> None:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO saved_hobbies(user_email, hobby_id, status, saved_at, meta)
                   VALUES (%s, %s, %s, now(), %s)
                   ON CONFLICT (user_email, hobby_id)
                   DO UPDATE SET status = EXCLUDED.status, saved_at = now(), meta = EXCLUDED.meta""",
                (user, hobby_id, status, Json(meta)),
            )

    def list_by_user(self, user: str) -> list[dict]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT hobby_id, status, saved_at, meta FROM saved_hobbies WHERE user_email=%s "
                "ORDER BY saved_at DESC",
                (user,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def update_status(self, user: str, hobby_id: str, status: str) -> bool:
        """영향받은 행이 있으면 True, 없으면(보관함에 없음) False를 반환한다."""
        with get_cursor() as cur:
            cur.execute(
                "UPDATE saved_hobbies SET status=%s WHERE user_email=%s AND hobby_id=%s",
                (status, user, hobby_id),
            )
            updated = cur.rowcount > 0
        return updated

    def delete(self, user: str, hobby_id: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                "DELETE FROM saved_hobbies WHERE user_email=%s AND hobby_id=%s",
                (user, hobby_id),
            )

    def count(self, user: str) -> int:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM saved_hobbies WHERE user_email=%s", (user,))
            row = cur.fetchone()
        return row["n"]
