# backend/repositories/user_repository.py
"""UserRepository — users 테이블(로그인한 유저 기본정보) 전용 데이터 접근 계층(PostgreSQL)."""
from db.connection import get_cursor


class UserRepository:
    def upsert(self, email: str, name: str, picture: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO users(email, name, picture, updated_at)
                   VALUES (%s, %s, %s, now())
                   ON CONFLICT (email)
                   DO UPDATE SET name = EXCLUDED.name, picture = EXCLUDED.picture,
                                 updated_at = now()""",
                (email, name, picture),
            )
