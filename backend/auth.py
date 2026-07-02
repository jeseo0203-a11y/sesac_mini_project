"""auth.py — Google OAuth2 + JWT (HS256). Planione auth.py를 MVP용으로 축소 포팅."""
import os
import time
import httpx
import jwt  # PyJWT
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import RedirectResponse

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
JWT_TTL = 60 * 60 * 24 * 30  # 30일

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v2/userinfo"


def make_jwt(user: dict) -> str:
    payload = {"sub": user["email"], "name": user.get("name", ""),
               "picture": user.get("picture", ""), "iat": int(time.time()),
               "exp": int(time.time()) + JWT_TTL}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_jwt(authorization: str = Header(default="")) -> dict:
    # 로컬 테스트용 우회: DEV_NO_AUTH=1 이면 로그인 없이 가짜 사용자로 통과(운영에선 절대 켜지 말 것)
    if os.getenv("DEV_NO_AUTH") == "1":
        return {"sub": "dev@local", "name": "로컬테스터", "picture": ""}
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "로그인이 필요합니다.")
    token = authorization.split(" ", 1)[1]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "토큰이 만료되었거나 유효하지 않습니다.")


@router.get("/auth/google/login")
def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(500, "GOOGLE_CLIENT_ID 미설정")
    url = (f"{GOOGLE_AUTH}?client_id={GOOGLE_CLIENT_ID}&redirect_uri={REDIRECT_URI}"
           f"&response_type=code&scope=openid%20email%20profile&access_type=offline&prompt=consent")
    return RedirectResponse(url)


@router.get("/auth/google/callback")
def google_callback(code: str = ""):
    if not code:
        raise HTTPException(400, "code 누락")
    with httpx.Client(timeout=15) as c:
        tok = c.post(GOOGLE_TOKEN, data={
            "code": code, "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET, "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"}).json()
        access = tok.get("access_token")
        if not access:
            raise HTTPException(401, f"토큰 교환 실패: {tok}")
        info = c.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access}"}).json()
    token = make_jwt({"email": info["email"], "name": info.get("name", ""),
                      "picture": info.get("picture", "")})
    # 프론트로 토큰 전달(URL hash) → 프론트가 localStorage 저장
    return RedirectResponse(f"{FRONTEND_URL}/#token={token}")


@router.get("/me")
def me(user: dict = Depends(verify_jwt)):
    return {"email": user["sub"], "name": user.get("name", ""), "picture": user.get("picture", "")}
