"""main.py — HobbyDNA MVP FastAPI 백엔드.
엔드포인트: 인증(Google) + 세션 + 메시지(대화/선택) + 피드백 + 리포트.
세션은 MVP용 인메모리 저장(단일 인스턴스). 실서비스는 PostgreSQL로 교체.
"""
import os
import uuid
from pathlib import Path
from typing import Optional


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

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth import router as auth_router, verify_jwt
from hobby_agents import (
    HybridConversationAgent, SelfImprovingRanker, GPTBackend, explain_hobby,
    HOBBY_CATALOG, hobby_public, hobby_by_id,
    HOBBY_CATEGORY, CATEGORY_LABEL, CATEGORY_EMOJI,
)

app = FastAPI(title="HobbyDNA MVP")

# ── SQLite 영속 저장(무드 기록·보관함) — 내장 sqlite3, 추가 설치 없음 ──
import sqlite3
import time as _time

DB_PATH = Path(__file__).with_name("hobbydna.db")

# 무드 프리셋(홈 컨디션 칩) — 에너지 힌트를 프로필 축에 반영
MOODS = [
    {"key": "tired", "label": "지쳐요", "emoji": "😮‍💨", "energy": 0.12},
    {"key": "relaxed", "label": "편안해요", "emoji": "😌", "energy": 0.35},
    {"key": "curious", "label": "궁금해요", "emoji": "🤔", "energy": 0.6},
    {"key": "energetic", "label": "활기차요", "emoji": "⚡", "energy": 0.85},
]


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS moods(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, mood TEXT,
            energy REAL, created_at INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS saved_hobbies(
            user TEXT, hobby_id TEXT, status TEXT, saved_at INTEGER, meta TEXT,
            PRIMARY KEY(user, hobby_id))""")
        # 기존 DB 마이그레이션(meta 컬럼 없으면 추가)
        cols = [r[1] for r in c.execute("PRAGMA table_info(saved_hobbies)").fetchall()]
        if "meta" not in cols:
            c.execute("ALTER TABLE saved_hobbies ADD COLUMN meta TEXT")


init_db()

# 사용자별 최신 리포트/진행중 세션(이어하기용, 인메모리 — 로컬 MVP)
LAST_REPORT: dict[str, dict] = {}

# CORS: 프론트(Vercel) 도메인 허용
_origins = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",")] + ["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router)

# 전역 자기개선 랭커(전역 학습=데이터 해자의 인메모리 근사). 실서비스는 DB 집계로.
GLOBAL_RANKER = SelfImprovingRanker()
SESSIONS: dict[str, HybridConversationAgent] = {}
GPT = GPTBackend()  # 취미 상세 설명용(스테이트리스)


class StartReq(BaseModel):
    pass


class MsgReq(BaseModel):
    session_id: str
    text: str = ""
    choice_index: Optional[int] = None
    choice_indices: Optional[list[int]] = None
    n_options: Optional[int] = None


class FbReq(BaseModel):
    session_id: str
    hobby_id: str
    kind: str
    reason: Optional[str] = None


@app.get("/")
def health():
    return {"ok": True, "service": "HobbyDNA MVP"}


@app.post("/session")
def start_session(_: StartReq = StartReq(), user: dict = Depends(verify_jwt)):
    sid = uuid.uuid4().hex
    SESSIONS[sid] = HybridConversationAgent(user_id=user["sub"], ranker=GLOBAL_RANKER)
    greeting = ("안녕하세요, 하비DNA예요. 오늘 당신의 마음을 진단해 딱 맞는 취미를 찾아드릴게요. "
                "요즘 마음이나 일상은 어떤가요? 편하게 한두 문장 들려주세요.")
    return {"session_id": sid, "message": {"type": "say", "text": greeting}}


def _agent(sid: str) -> HybridConversationAgent:
    ag = SESSIONS.get(sid)
    if not ag:
        raise HTTPException(404, "세션이 없어요. 새로고침 후 다시 시작해 주세요.")
    return ag


@app.post("/message")
def message(req: MsgReq, user: dict = Depends(verify_jwt)):
    ag = _agent(req.session_id)
    out = ag.send(req.text, choice_index=req.choice_index,
                  choice_indices=req.choice_indices, n_options=req.n_options)
    if out.get("type") == "report":
        LAST_REPORT[user["sub"]] = out.get("report", {})
    return {"message": out}


@app.post("/feedback")
def feedback(req: FbReq, user: dict = Depends(verify_jwt)):
    ag = _agent(req.session_id)
    out = ag.feedback(req.hobby_id, req.kind, req.reason)
    if out.get("type") == "report":
        LAST_REPORT[user["sub"]] = out.get("report", {})
    return {"message": out}


# ──────────────────────────────────────────────────────────────────────────────
# 리뉴얼 신규 API — 홈 / 무드 / 보관함 / 카테고리
# ──────────────────────────────────────────────────────────────────────────────
class MoodReq(BaseModel):
    mood: str


class SaveReq(BaseModel):
    hobby_id: str
    status: str = "관심 있음"
    meta: Optional[dict] = None  # 카탈로그 밖(커스텀) 취미 저장용 전체 메타


class StatusReq(BaseModel):
    hobby_id: str
    status: str


@app.get("/home")
def home(user: dict = Depends(verify_jwt)):
    sub = user["sub"]
    # 데일리 추천: 최신 리포트 1위, 없으면 회복형 기본 추천(식물)
    rep = LAST_REPORT.get(sub)
    if rep and rep.get("items"):
        top_id = rep["items"][0]["id"]
        featured = hobby_public(hobby_by_id(top_id))
        featured["why"] = rep["items"][0].get("why", "")
    else:
        featured = hobby_public(hobby_by_id("plant"))
        featured["why"] = "가볍게 시작하기 좋은, 회복에 도움이 되는 취미예요."
    with _db() as c:
        today = _time.strftime("%Y-%m-%d")
        row = c.execute(
            "SELECT mood FROM moods WHERE user=? AND date(created_at,'unixepoch')=? "
            "ORDER BY id DESC LIMIT 1", (sub, today)).fetchone()
        saved_cnt = c.execute("SELECT COUNT(*) n FROM saved_hobbies WHERE user=?",
                              (sub,)).fetchone()["n"]
    cats = [{"key": k, "label": v, "emoji": CATEGORY_EMOJI.get(k, "🎯")}
            for k, v in CATEGORY_LABEL.items()]
    return {
        "name": user.get("name") or "친구", "picture": user.get("picture", ""),
        "moods": MOODS, "today_mood": row["mood"] if row else None,
        "featured": featured, "categories": cats,
        "has_report": bool(rep), "in_progress": sub in SESSIONS, "saved_count": saved_cnt,
    }


@app.post("/mood")
def set_mood(req: MoodReq, user: dict = Depends(verify_jwt)):
    m = next((x for x in MOODS if x["key"] == req.mood), None)
    if not m:
        raise HTTPException(400, "알 수 없는 무드")
    with _db() as c:
        c.execute("INSERT INTO moods(user,mood,energy,created_at) VALUES(?,?,?,?)",
                  (user["sub"], m["key"], m["energy"], int(_time.time())))
    return {"ok": True, "mood": m}


@app.get("/moods")
def get_moods(user: dict = Depends(verify_jwt)):
    with _db() as c:
        rows = c.execute("SELECT mood,energy,created_at FROM moods WHERE user=? "
                         "ORDER BY id DESC LIMIT 30", (user["sub"],)).fetchall()
    return {"moods": [dict(r) for r in rows]}


class DetailReq(BaseModel):
    hobby_id: str
    meta: Optional[dict] = None


@app.post("/hobby_detail")
def hobby_detail(req: DetailReq, user: dict = Depends(verify_jwt)):
    # 취미 메타 해석: 카탈로그 → 클라 meta → 최신 리포트 아이템
    h = hobby_by_id(req.hobby_id)
    meta = hobby_public(h) if h else req.meta
    if not meta:
        rep = LAST_REPORT.get(user["sub"])
        if rep:
            meta = next((it for it in rep.get("items", []) if it.get("id") == req.hobby_id), None)
    if not meta:
        raise HTTPException(404, "취미 정보를 찾을 수 없어요")
    # 사용자 성향(있으면 개인화)
    rep = LAST_REPORT.get(user["sub"])
    axis = (rep.get("profile", {}) or {}).get("axis") if rep else None
    detail = explain_hobby(meta, axis, GPT)
    return {"hobby": meta, "detail": detail, "personalized": bool(axis)}


@app.get("/categories")
def categories():
    out = []
    for k, label in CATEGORY_LABEL.items():
        items = [hobby_public(h) for h in HOBBY_CATALOG if HOBBY_CATEGORY.get(h.id) == k]
        out.append({"key": k, "label": label, "emoji": CATEGORY_EMOJI.get(k, "🎯"),
                    "items": items})
    return {"categories": out}


@app.post("/save")
def save_hobby(req: SaveReq, user: dict = Depends(verify_jwt)):
    import json as _json
    h = hobby_by_id(req.hobby_id)
    # 카탈로그에 있으면 서버 메타, 없으면(커스텀) 클라이언트가 보낸 meta 사용
    meta = hobby_public(h) if h else req.meta
    if not meta:
        raise HTTPException(404, "취미 정보를 찾을 수 없어요(meta 필요)")
    with _db() as c:
        c.execute("INSERT OR REPLACE INTO saved_hobbies(user,hobby_id,status,saved_at,meta) "
                  "VALUES(?,?,?,?,?)", (user["sub"], req.hobby_id, req.status,
                                        int(_time.time()), _json.dumps(meta, ensure_ascii=False)))
    return {"ok": True}


@app.get("/library")
def library(user: dict = Depends(verify_jwt)):
    import json as _json
    with _db() as c:
        rows = c.execute("SELECT hobby_id,status,saved_at,meta FROM saved_hobbies WHERE user=? "
                         "ORDER BY saved_at DESC", (user["sub"],)).fetchall()
    items = []
    for r in rows:
        it = None
        if r["meta"]:
            try:
                it = _json.loads(r["meta"])
            except Exception:
                it = None
        if it is None:
            h = hobby_by_id(r["hobby_id"])
            if not h:
                continue
            it = hobby_public(h)
        it["id"] = r["hobby_id"]
        it["status"] = r["status"]
        it["saved_at"] = _time.strftime("%Y.%m.%d", _time.localtime(r["saved_at"]))
        items.append(it)
    return {"items": items}


@app.patch("/library")
def update_status(req: StatusReq, user: dict = Depends(verify_jwt)):
    with _db() as c:
        cur = c.execute("UPDATE saved_hobbies SET status=? WHERE user=? AND hobby_id=?",
                        (req.status, user["sub"], req.hobby_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "보관함에 없는 취미")
    return {"ok": True}


@app.delete("/library/{hobby_id}")
def remove_saved(hobby_id: str, user: dict = Depends(verify_jwt)):
    with _db() as c:
        c.execute("DELETE FROM saved_hobbies WHERE user=? AND hobby_id=?",
                  (user["sub"], hobby_id))
    return {"ok": True}
