# backend/main.py
"""main.py — HobbyDNA MVP FastAPI 백엔드 엔트리포인트.
Controller(routers) → Service → Repository 3계층 구조로 분리되어 있으며,
이 파일은 앱 조립(환경변수 로드 · 라우터 등록 · 미들웨어 · DB 초기화)만 담당한다.
실제 비즈니스 로직은 services/*, DB 접근은 repositories/*에 있다.
"""
import os
from pathlib import Path


def _load_dotenv():
    """auth import 전에 .env를 os.environ에 주입(의존성 없는 최소 로더).
    이미 셸에 설정된 환경변수는 덮어쓰지 않는다."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        # 값 뒤 인라인 주석(' #...') 제거 + 따옴표 제거
        val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import router as auth_router
from db.connection import init_db
from routers.home_router import router as home_router
from routers.hobby_router import router as hobby_router
from routers.library_router import router as library_router
from routers.mood_router import router as mood_router
from routers.session_router import router as session_router

app = FastAPI(title="HobbyDNA MVP")

# SQLite 영속 저장(무드 기록·보관함) 테이블 초기화
init_db()

# CORS: 프론트(Vercel) 도메인 허용
# 브라우저 Origin 헤더는 끝에 '/'가 절대 붙지 않으므로, 허용 목록도 끝 슬래시를 제거해
# 정확히 일치시켜야 한다(안 그러면 로그인 후 API 호출이 CORS로 막힌다).
_origins = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip().rstrip("/") for o in _origins.split(",")] + ["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(session_router)
app.include_router(home_router)
app.include_router(mood_router)
app.include_router(hobby_router)
app.include_router(library_router)


@app.get("/")
def health():
    return {"ok": True, "service": "HobbyDNA MVP"}
