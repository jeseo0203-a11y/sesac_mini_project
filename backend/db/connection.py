# backend/db/connection.py
"""PostgreSQL 연결 및 테이블 초기화 — Repository 계층 전용 저수준 DB 접근.
DATABASE_URL 하나로 연결한다(Railway에 Postgres 플러그인을 추가하면 자동 주입됨).
"""
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL이 설정되지 않았습니다. Railway에서는 Postgres 플러그인을 추가하면 "
            "자동으로 주입되고, 로컬에서는 Railway 대시보드(Variables 탭)에서 같은 값을 "
            "복사해 .env에 넣으세요."
        )
    # Railway/구버전 Postgres가 'postgres://' 스킴을 줄 때가 있어 명시적으로 정규화한다.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


@contextmanager
def get_cursor():
    """호출마다 새 커넥션을 열고 RealDictCursor(딕셔너리처럼 컬럼 접근)를 내어준다.
    with 블록이 정상 종료되면 commit, 예외가 나면 rollback 후 항상 커넥션을 닫는다."""
    conn = psycopg2.connect(_database_url(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """앱 기동 시 1회 호출. 테이블이 없으면 생성한다(IF NOT EXISTS라 여러 번 호출해도 안전)."""
    with get_cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS users(
            email TEXT PRIMARY KEY,
            name TEXT,
            picture TEXT,
            updated_at TIMESTAMPTZ DEFAULT now())""")
        cur.execute("""CREATE TABLE IF NOT EXISTS moods(
            id SERIAL PRIMARY KEY,
            user_email TEXT NOT NULL,
            mood TEXT,
            energy REAL,
            created_at TIMESTAMPTZ DEFAULT now())""")
        cur.execute("""CREATE TABLE IF NOT EXISTS saved_hobbies(
            user_email TEXT NOT NULL,
            hobby_id TEXT NOT NULL,
            status TEXT,
            saved_at TIMESTAMPTZ DEFAULT now(),
            meta JSONB,
            PRIMARY KEY(user_email, hobby_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS hobby_reports(
            id SERIAL PRIMARY KEY,
            user_email TEXT NOT NULL,
            report JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now())""")
