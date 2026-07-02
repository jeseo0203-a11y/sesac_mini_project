"""hobby_agents.py — HobbyDNA(하비DNA) 취미 발굴 AI 에이전트 (단일 모듈, MVP)
================================================================================
Planione `agent.py`(도구호출 루프 + ask_user 하이브리드)와 `self_improve.py`(자기개선
순수 로직)를 포팅. 미니체험(③)은 제외.

★ 이 버전의 핵심: GPT가 '판단·분석'해서 선택지를 동적으로 만든다.
  - ask_user 옵션은 고정 목록이 아니라, 직전 대화를 분석해 GPT가 그 자리에서 생성한다.
  - '왜 이 취미인지' 설명도 GPT가 사용자 좌표를 보고 문장으로 쓴다.
  - OPENAI_API_KEY가 없을 때만 결정적 오프라인 스텁으로 폴백(개발/CI용).

의존성: 표준 라이브러리 + (선택) numpy + (선택) openai
실행:  python hobby_agents.py        # 오프라인 데모
================================================================================
"""
from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

# ──────────────────────────────────────────────────────────────────────────────
# 0. 설정
# ──────────────────────────────────────────────────────────────────────────────
GPT_MODEL = os.getenv("HOBBY_GPT_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.getenv("HOBBY_EMBED_MODEL", "text-embedding-3-small")

HOBBY_AXES: Dict[str, Tuple[str, str]] = {
    "energy":     ("고갈/회복필요", "충만/발산"),
    "motivation": ("해소/회복",     "성취/창작"),
    "social":     ("혼자",          "함께"),
    "activity":   ("정적",          "격한운동"),
    "achievement":("과정/기록",     "결과물/완성"),
    "time":       ("짧게(10분)",    "길게(몰입)"),
    "budget":     ("0원",           "장비형(고비용)"),
    "space":      ("집(homebody)",  "탐험(explorer)"),
    "novelty":    ("익숙함",        "새로움"),
}
AXIS_KEYS: List[str] = list(HOBBY_AXES.keys())
CORE_AXES: List[str] = ["energy", "social", "activity", "budget", "time"]


# ──────────────────────────────────────────────────────────────────────────────
# 1. 취미 지식베이스 (RAG 시드)
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Hobby:
    id: str
    name: str
    tags: List[str]
    axis: Dict[str, float]
    cost_per_month: str
    equipment: str
    difficulty: str
    time_needed: str
    daynight: str
    first_spark: str

    def vector(self) -> List[float]:
        return [float(self.axis.get(k, 0.5)) for k in AXIS_KEYS]


HOBBY_CATALOG: List[Hobby] = [
    Hobby("plant", "식물 키우기/물주기", ["회복", "정적", "혼자", "저비용", "집"],
          {"energy": 0.1, "motivation": 0.2, "social": 0.05, "activity": 0.1,
           "achievement": 0.3, "time": 0.1, "budget": 0.15, "space": 0.1, "novelty": 0.3},
          "5천~2만원/월", "화분·흙·작은 식물", "입문 매우 쉬움", "하루 5분", "아침/저녁 모두",
          "오늘 밤, 작은 다육이 하나 물 주고 잎 사진 한 장 찍기."),
    Hobby("sketch", "10분 드로잉/필사", ["회복", "정적", "혼자", "기록", "저비용", "집"],
          {"energy": 0.2, "motivation": 0.45, "social": 0.1, "activity": 0.1,
           "achievement": 0.4, "time": 0.15, "budget": 0.1, "space": 0.1, "novelty": 0.4},
          "1만원/월", "펜·노트", "쉬움", "10~20분", "저녁/야행성 적합",
          "오늘 밤 10분, 좋아하는 사진 한 장 보고 따라 그리기."),
    Hobby("baking", "베이킹", ["성취", "과정", "느슨한연대", "중간비용", "집"],
          {"energy": 0.45, "motivation": 0.7, "social": 0.35, "activity": 0.35,
           "achievement": 0.75, "time": 0.6, "budget": 0.45, "space": 0.15, "novelty": 0.5},
          "3만~6만원/월", "오븐·기본 베이킹툴", "보통", "1~2시간", "주말 낮 적합",
          "이번 주말, 머핀 1판 레시피 하나 따라 굽기."),
    Hobby("running", "러닝/러닝크루", ["발산", "운동", "함께", "도전", "저비용", "탐험"],
          {"energy": 0.85, "motivation": 0.7, "social": 0.7, "activity": 0.9,
           "achievement": 0.6, "time": 0.4, "budget": 0.2, "space": 0.9, "novelty": 0.5},
          "0~3만원/월", "러닝화", "보통", "30~50분", "아침/저녁",
          "내일 아침, 동네 한 바퀴 15분만 가볍게 뛰기."),
    Hobby("climbing", "클라이밍", ["발산", "운동", "함께", "도전", "중간비용", "탐험"],
          {"energy": 0.9, "motivation": 0.8, "social": 0.65, "activity": 0.95,
           "achievement": 0.8, "time": 0.6, "budget": 0.6, "space": 0.8, "novelty": 0.75},
          "8만~15만원/월", "클라이밍화(대여 가능)", "처음엔 어려움", "1.5시간", "저녁 적합",
          "이번 주, 집 근처 암장 1회 체험 클래스 예약하기."),
    Hobby("band", "밴드/악기 합주", ["발산", "창작", "함께", "커뮤니티", "고비용", "탐험"],
          {"energy": 0.75, "motivation": 0.85, "social": 0.85, "activity": 0.5,
           "achievement": 0.7, "time": 0.7, "budget": 0.7, "space": 0.6, "novelty": 0.7},
          "10만원+/월", "악기·합주실 대여", "보통~어려움", "2시간", "저녁/주말",
          "이번 주, 유튜브로 좋아하는 곡 코드 3개 따라 쳐보기."),
    Hobby("calligraphy", "캘리그라피/손글씨", ["회복", "창작", "혼자", "기록", "저비용", "집"],
          {"energy": 0.3, "motivation": 0.55, "social": 0.1, "activity": 0.15,
           "achievement": 0.6, "time": 0.3, "budget": 0.2, "space": 0.1, "novelty": 0.45},
          "2만원/월", "붓펜·연습지", "쉬움~보통", "20~40분", "저녁 적합",
          "오늘 밤, 좋아하는 문장 하나를 붓펜으로 천천히 써보기."),
    Hobby("photo", "사진/산책 사진", ["발산", "탐험", "혼자", "기록", "저비용", "탐험"],
          {"energy": 0.55, "motivation": 0.6, "social": 0.25, "activity": 0.5,
           "achievement": 0.55, "time": 0.4, "budget": 0.3, "space": 0.85, "novelty": 0.65},
          "0~5만원/월", "스마트폰이면 충분", "쉬움", "30분~", "낮 적합",
          "내일 점심, 동네 한 골목 걸으며 마음에 드는 장면 3컷 찍기."),
    Hobby("cooking", "집밥/한 그릇 요리", ["성취", "과정", "혼자", "저비용", "집"],
          {"energy": 0.4, "motivation": 0.55, "social": 0.2, "activity": 0.3,
           "achievement": 0.6, "time": 0.4, "budget": 0.35, "space": 0.1, "novelty": 0.4},
          "식재료비", "기본 조리도구", "쉬움", "30~40분", "저녁 적합",
          "오늘 저녁, 좋아하는 한 그릇 요리 하나 레시피 보고 만들기."),
    Hobby("puzzle", "퍼즐/보드게임(솔로)", ["회복", "정적", "혼자", "몰입", "저비용", "집"],
          {"energy": 0.35, "motivation": 0.4, "social": 0.2, "activity": 0.1,
           "achievement": 0.5, "time": 0.45, "budget": 0.25, "space": 0.1, "novelty": 0.5},
          "1만~3만원/월", "퍼즐·보드게임", "쉬움", "30분~", "저녁/야행성",
          "오늘 밤, 작은 직소퍼즐 한 코너만 맞춰보기."),
]


# 취미별 표시용 메타(카테고리·이모지) — Stitch 리뉴얼 홈/탐색/보관함에서 사용
HOBBY_EMOJI: Dict[str, str] = {
    "plant": "🪴", "sketch": "✏️", "baking": "🧁", "running": "🏃", "climbing": "🧗",
    "band": "🎸", "calligraphy": "🖋️", "photo": "📷", "cooking": "🍳", "puzzle": "🧩",
}
HOBBY_CATEGORY: Dict[str, str] = {
    "sketch": "creative", "calligraphy": "creative", "band": "creative", "photo": "creative",
    "running": "active", "climbing": "active",
    "plant": "healing", "puzzle": "healing",
    "baking": "craft", "cooking": "craft",
}
CATEGORY_LABEL: Dict[str, str] = {
    "creative": "창의적 예술", "active": "활동적인 운동",
    "healing": "마음 회복", "craft": "만들기·요리",
}
CATEGORY_EMOJI: Dict[str, str] = {
    "creative": "🎨", "active": "🏃", "healing": "🌿", "craft": "🧑‍🍳",
}

# 카탈로그 확장 — 탐색하기 다양성 + 추천 폭 확대
# (id, name, category, emoji, tags, cost, equip, difficulty, time, daynight, first_spark, axis_core)
_EXTRA_HOBBIES = [
    ("watercolor", "수채화 그리기", "creative", "🎨", ["창작", "정적", "혼자", "기록"],
     "2~4만원/월", "물감·붓·종이", "쉬움~보통", "30~40분", "저녁/주말",
     "오늘 좋아하는 색 하나로 작은 종이에 번지기 연습.",
     {"energy": 0.35, "social": 0.15, "activity": 0.2, "budget": 0.35, "time": 0.5, "motivation": 0.6}),
    ("ukulele", "우쿨렐레", "creative", "🎵", ["창작", "혼자", "입문쉬움"],
     "3~6만원/월", "우쿨렐레", "쉬움", "20~40분", "저녁",
     "오늘 유튜브로 코드 2개(C·Am) 잡아보기.",
     {"energy": 0.5, "social": 0.3, "activity": 0.3, "budget": 0.4, "time": 0.4, "motivation": 0.7, "novelty": 0.6}),
    ("writing", "에세이·짧은 글쓰기", "creative", "📝", ["창작", "혼자", "기록", "저비용"],
     "0~1만원/월", "노트·메모앱", "쉬움", "15~30분", "밤",
     "오늘 있었던 일을 세 줄로 적어보기.",
     {"energy": 0.35, "social": 0.1, "activity": 0.15, "budget": 0.1, "time": 0.4, "motivation": 0.7}),
    ("video", "영상·브이로그 편집", "creative", "🎬", ["창작", "혼자", "기록", "도전"],
     "0~3만원/월", "스마트폰·편집앱", "보통", "1시간~", "저녁/주말",
     "오늘 찍은 영상 15초로 잘라 자막 한 줄 넣기.",
     {"energy": 0.55, "social": 0.3, "activity": 0.3, "budget": 0.3, "time": 0.65, "motivation": 0.8, "novelty": 0.7}),
    ("digitaldraw", "디지털 드로잉", "creative", "🖌️", ["창작", "혼자", "도전"],
     "0~5만원/월", "태블릿·앱", "보통", "30분~", "밤",
     "오늘 좋아하는 캐릭터 하나 따라 그리기.",
     {"energy": 0.4, "social": 0.15, "activity": 0.2, "budget": 0.4, "time": 0.55, "motivation": 0.75, "novelty": 0.65}),
    ("homeworkout", "홈트·맨몸운동", "active", "💪", ["운동", "혼자", "저비용"],
     "0~2만원/월", "매트", "쉬움~보통", "20~30분", "아침/저녁",
     "오늘 스쿼트 15개 한 세트만.",
     {"energy": 0.75, "social": 0.15, "activity": 0.8, "budget": 0.15, "time": 0.35}),
    ("badminton", "배드민턴", "active", "🏸", ["운동", "함께", "도전"],
     "2~5만원/월", "라켓·셔틀콕", "쉬움", "1시간", "저녁/주말",
     "오늘 친구에게 한 판 치자고 메시지 보내기.",
     {"energy": 0.8, "social": 0.75, "activity": 0.8, "budget": 0.35, "time": 0.5}),
    ("cycling", "자전거 라이딩", "active", "🚴", ["운동", "탐험", "혼자"],
     "0~5만원/월", "자전거·헬멧", "보통", "1시간~", "낮",
     "오늘 동네 한 바퀴 10분만 타보기.",
     {"energy": 0.8, "social": 0.35, "activity": 0.8, "budget": 0.4, "time": 0.55, "novelty": 0.5}),
    ("swimming", "수영", "active", "🏊", ["운동", "혼자", "회복"],
     "5~10만원/월", "수영복·수경", "보통", "40분", "아침/저녁",
     "이번 주 동네 수영장 자유수영 시간 알아보기.",
     {"energy": 0.7, "social": 0.3, "activity": 0.85, "budget": 0.5, "time": 0.5}),
    ("hiking", "등산·트레킹", "active", "🥾", ["운동", "탐험", "함께", "회복"],
     "0~5만원/월", "운동화·물", "쉬움~보통", "2시간~", "낮",
     "이번 주말 가까운 낮은 산 하나 검색해보기.",
     {"energy": 0.7, "social": 0.5, "activity": 0.75, "budget": 0.3, "time": 0.7, "novelty": 0.55}),
    ("tennis", "테니스", "active", "🎾", ["운동", "함께", "도전", "고비용"],
     "10만원+/월", "라켓·코트", "어려움", "1~2시간", "저녁/주말",
     "이번 주 원데이 레슨 하나 알아보기.",
     {"energy": 0.85, "social": 0.7, "activity": 0.9, "budget": 0.7, "time": 0.6}),
    ("yoga", "요가·스트레칭", "healing", "🧘", ["회복", "혼자", "정적"],
     "0~5만원/월", "매트", "쉬움", "20~30분", "아침/저녁",
     "오늘 자기 전 5분 스트레칭 3동작.",
     {"energy": 0.3, "social": 0.2, "activity": 0.4, "budget": 0.25, "time": 0.4}),
    ("meditation", "명상·호흡", "healing", "🌬️", ["회복", "혼자", "정적", "저비용"],
     "0원/월", "앱(선택)", "매우 쉬움", "5~15분", "밤",
     "오늘 눈 감고 호흡 10번만 세어보기.",
     {"energy": 0.2, "social": 0.1, "activity": 0.1, "budget": 0.05, "time": 0.2}),
    ("homecafe", "홈카페·티타임", "healing", "🍵", ["회복", "혼자", "기록"],
     "1~3만원/월", "티·드리퍼", "쉬움", "20분", "오후/저녁",
     "오늘 좋아하는 차 한 잔 예쁘게 내려 사진 찍기.",
     {"energy": 0.35, "social": 0.25, "activity": 0.2, "budget": 0.3, "time": 0.3}),
    ("coloring", "컬러링북", "healing", "🖍️", ["회복", "혼자", "정적", "저비용"],
     "1만원/월", "컬러링북·색연필", "매우 쉬움", "20~30분", "밤",
     "오늘 한 칸만 색칠하고 자기.",
     {"energy": 0.25, "social": 0.1, "activity": 0.15, "budget": 0.2, "time": 0.35}),
    ("journaling", "감사일기·저널링", "healing", "📔", ["회복", "혼자", "기록", "저비용"],
     "0~1만원/월", "노트·펜", "매우 쉬움", "10분", "밤",
     "오늘 감사한 일 한 가지 적어보기.",
     {"energy": 0.3, "social": 0.1, "activity": 0.1, "budget": 0.1, "time": 0.25}),
    ("pottery", "도예·원데이 클래스", "craft", "🏺", ["창작", "과정", "함께", "중간비용"],
     "5~10만원/월", "공방(대여)", "보통", "2시간", "주말",
     "이번 주 근처 도예 원데이 클래스 검색해보기.",
     {"energy": 0.5, "social": 0.5, "activity": 0.4, "budget": 0.55, "time": 0.65, "motivation": 0.7, "novelty": 0.7}),
    ("knitting", "뜨개질", "craft", "🧶", ["회복", "과정", "혼자", "저비용"],
     "1~3만원/월", "실·바늘", "쉬움~보통", "30분~", "밤",
     "오늘 유튜브 보고 첫 코 10개만 잡기.",
     {"energy": 0.3, "social": 0.15, "activity": 0.2, "budget": 0.25, "time": 0.5, "motivation": 0.65}),
    ("leather", "가죽공예", "craft", "🧳", ["창작", "과정", "혼자", "중간비용"],
     "3~7만원/월", "가죽·공구 키트", "보통", "1~2시간", "저녁/주말",
     "오늘 카드지갑 키트 하나 장바구니에 담아보기.",
     {"energy": 0.45, "social": 0.2, "activity": 0.35, "budget": 0.55, "time": 0.6, "motivation": 0.7, "novelty": 0.65}),
    ("coffeebrew", "핸드드립 커피", "craft", "☕", ["과정", "혼자", "기록"],
     "2~4만원/월", "드리퍼·원두", "쉬움~보통", "15분", "아침",
     "오늘 아침 원두 한 봉 사서 한 잔 내려보기.",
     {"energy": 0.4, "social": 0.2, "activity": 0.25, "budget": 0.35, "time": 0.3, "motivation": 0.6}),
    ("woodwork", "목공·소품 DIY", "craft", "🪚", ["창작", "과정", "도전", "중간비용"],
     "3~8만원/월", "공구·목재", "보통~어려움", "2시간", "주말",
     "오늘 만들고 싶은 작은 소품 하나 검색해보기.",
     {"energy": 0.55, "social": 0.25, "activity": 0.5, "budget": 0.6, "time": 0.7, "motivation": 0.75, "novelty": 0.6}),
    ("candle", "캔들·비누 만들기", "craft", "🕯️", ["창작", "과정", "혼자", "회복"],
     "2~5만원/월", "왁스·향료 키트", "쉬움", "1시간", "저녁",
     "오늘 좋아하는 향 하나 골라 키트 알아보기.",
     {"energy": 0.4, "social": 0.25, "activity": 0.3, "budget": 0.4, "time": 0.5, "motivation": 0.65}),
]

for _s in _EXTRA_HOBBIES:
    _hid, _name, _cat, _emoji, _tags, _cost, _equip, _diff, _tm, _dn, _spark, _ax = _s
    _axis = {k: 0.5 for k in AXIS_KEYS}
    _axis.update(_ax)
    HOBBY_CATALOG.append(Hobby(id=_hid, name=_name, tags=_tags, axis=_axis,
                               cost_per_month=_cost, equipment=_equip, difficulty=_diff,
                               time_needed=_tm, daynight=_dn, first_spark=_spark))
    HOBBY_EMOJI[_hid] = _emoji
    HOBBY_CATEGORY[_hid] = _cat


def hobby_by_id(hid: str) -> Optional["Hobby"]:
    return next((h for h in HOBBY_CATALOG if h.id == hid), None)


def hobby_public(h: "Hobby") -> Dict[str, Any]:
    """API 응답용 취미 메타(홈·탐색·보관함 카드에 필요한 필드)."""
    cat = HOBBY_CATEGORY.get(h.id, "creative")
    return {
        "id": h.id, "name": h.name, "emoji": HOBBY_EMOJI.get(h.id, "🎯"),
        "category": cat, "category_label": CATEGORY_LABEL.get(cat, "취미"),
        "tags": h.tags[:3], "cost": h.cost_per_month, "equipment": h.equipment,
        "difficulty": h.difficulty, "time": h.time_needed, "daynight": h.daynight,
        "first_spark": h.first_spark,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2. 벡터 유틸
# ──────────────────────────────────────────────────────────────────────────────
def _cosine(a: List[float], b: List[float]) -> float:
    if _np is not None:
        va, vb = _np.asarray(a, float), _np.asarray(b, float)
        na, nb = float(_np.linalg.norm(va)), float(_np.linalg.norm(vb))
        return float(va @ vb / (na * nb)) if na and nb else 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 3. 사용자 프로파일
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class HobbyProfile:
    user_id: str
    axis: Dict[str, float] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)
    axis_weight: Dict[str, float] = field(default_factory=lambda: {k: 1.0 for k in AXIS_KEYS})
    raw_signals: List[str] = field(default_factory=list)
    tried: set = field(default_factory=set)
    burnout: float = 0.0

    def set_axis(self, key: str, value: float, conf: float = 0.8) -> None:
        if key not in HOBBY_AXES:
            return
        value = max(0.0, min(1.0, value))
        old, oc = self.axis.get(key), self.confidence.get(key, 0.0)
        if old is None:
            self.axis[key], self.confidence[key] = value, conf
        else:
            total = oc + conf
            self.axis[key] = (old * oc + value * conf) / total if total else value
            self.confidence[key] = min(1.0, total)

    def vector(self) -> List[float]:
        return [float(self.axis.get(k, 0.5)) for k in AXIS_KEYS]

    def completeness(self) -> float:
        return sum(self.confidence.get(k, 0.0) for k in CORE_AXES) / len(CORE_AXES)

    def missing_core(self) -> List[str]:
        return [k for k in CORE_AXES if self.confidence.get(k, 0.0) < 0.5]

    def to_dict(self) -> Dict[str, Any]:
        return {"axis": self.axis, "confidence": self.confidence,
                "burnout": self.burnout, "tried": list(self.tried)}


# ──────────────────────────────────────────────────────────────────────────────
# 4. LLM 백엔드 — GPT API (없으면 결정적 오프라인 스텁)
# ──────────────────────────────────────────────────────────────────────────────
class _OfflineLLM:
    """OPENAI_API_KEY가 없을 때만 쓰는 폴백. 데모/CI가 인프라 없이 돌도록 흐름을 흉내낸다.
    (실서비스에서는 GPT가 동적으로 선택지를 만들기 때문에 이 고정 목록은 쓰이지 않는다.)"""

    def __init__(self) -> None:
        self._asked = 0

    def chat(self, messages, tools=None, **_) -> Dict[str, Any]:
        order = [
            ("energy", "요즘 마음의 에너지는 어느 쪽에 가까워요?",
             ["거의 방전이에요", "조금 지쳐요", "그럭저럭이요", "꽤 충전돼 있어요"]),
            ("social", "취미를 즐길 때 어떤 결이 편해요?",
             ["오롯이 혼자", "가끔 느슨하게", "둘 다 좋아요", "사람들과 함께"]),
            ("activity", "몸을 쓰는 정도는 어느 쪽이 끌려요?",
             ["가만히 몰입", "가볍게 손만", "적당히 움직이기", "땀 흘리는 활동"]),
            ("budget", "이번 달, 취미에 쓸 수 있는 예산은?",
             ["0원에 가깝게", "월 1~2만원", "월 3~5만원", "장비 투자도 OK"]),
            ("time", "한 번에 낼 수 있는 시간은?",
             ["10분 안팎", "20~30분", "30분~1시간", "푹 몰입할 수 있어요"]),
        ]
        if self._asked < len(order):
            axis, q, opts = order[self._asked]
            self._asked += 1
            return {"text": "", "tool_calls": [{"name": "ask_user",
                    "arguments": {"question": q, "options": opts, "axis_hint": axis}}]}
        self._asked += 1
        phase = self._asked - len(order)
        if phase == 1:
            return {"text": "", "tool_calls": [{"name": "recommend_hobbies", "arguments": {"top_k": 3}}]}
        if phase == 2:
            return {"text": "회복이 필요한 지금에 맞춰 골라봤어요. 마음에 안 드는 게 있으면 말해줘요.",
                    "tool_calls": []}
        return {"text": "", "tool_calls": [{"name": "finalize_report", "arguments": {}}]}

    def complete(self, system, user) -> str:
        return ""


class GPTBackend:
    """OpenAI Chat Completions(function calling) 래퍼.
    online이면 GPT가 직접 선택지/설명을 동적 생성. 키 없으면 _OfflineLLM 폴백."""

    def __init__(self) -> None:
        self.online = False
        self._client = None
        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                self._client = OpenAI()
                self.online = True
            except Exception as e:
                print(f"[hobby] openai 사용 불가 → 오프라인 스텁: {e}")
        if not self.online:
            self._offline = _OfflineLLM()

    def chat(self, messages: List[Dict], tools: List[Dict],
             tool_choice: str = "auto") -> Dict[str, Any]:
        if not self.online:
            return self._offline.chat(messages, tools)
        resp = self._client.chat.completions.create(
            model=GPT_MODEL, messages=messages,
            tools=[{"type": "function", "function": t} for t in tools],
            tool_choice=tool_choice, temperature=0.7,
        )
        msg = resp.choices[0].message
        calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
        return {"text": msg.content or "", "tool_calls": calls}

    def complete(self, system: str, user: str, temperature: float = 0.7) -> str:
        """자유형 1회 완성 — '왜 이 취미인지' 같은 분석/설명 생성용."""
        if not self.online:
            return self._offline.complete(system, user)
        try:
            r = self._client.chat.completions.create(
                model=GPT_MODEL, temperature=temperature,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            return (r.choices[0].message.content or "").strip()
        except Exception:
            return ""

    def embed(self, text: str) -> Optional[List[float]]:
        if not self.online:
            return None
        try:
            r = self._client.embeddings.create(model=EMBED_MODEL, input=text[:8000])
            return r.data[0].embedding
        except Exception:
            return None


# ──────────────────────────────────────────────────────────────────────────────
# 5. 신호 분석
# ──────────────────────────────────────────────────────────────────────────────
_AXIS_RULES: Dict[str, List[Tuple[str, float]]] = {
    "energy":   [("지친", 0.1), ("번아웃", 0.05), ("방전", 0.05), ("쉬고", 0.2),
                 ("에너지", 0.8), ("활력", 0.85), ("신나", 0.9)],
    "social":   [("혼자", 0.05), ("내향", 0.1), ("조용", 0.2),
                 ("같이", 0.85), ("사람", 0.8), ("모임", 0.9), ("친구", 0.8)],
    "activity": [("정적", 0.1), ("앉아", 0.15), ("차분", 0.2),
                 ("운동", 0.85), ("땀", 0.9), ("뛰", 0.85), ("격한", 0.95)],
    "budget":   [("돈없", 0.05), ("무료", 0.05), ("저렴", 0.2),
                 ("장비", 0.8), ("투자", 0.85)],
    "time":     [("짧", 0.15), ("10분", 0.1), ("바쁘", 0.2),
                 ("몰입", 0.85), ("푹", 0.8), ("길게", 0.85)],
    "motivation":[("해소", 0.15), ("스트레스", 0.2), ("힐링", 0.15),
                 ("성취", 0.85), ("만들", 0.8), ("창작", 0.9)],
    "novelty":  [("익숙", 0.15), ("늘 하던", 0.1),
                 ("새로운", 0.85), ("처음", 0.8), ("도전", 0.85)],
}
_BURNOUT_RULES = ["번아웃", "방전", "지쳤", "소진", "무기력", "우울", "힘들어"]


class SignalIngestor:
    def __init__(self, gpt: GPTBackend) -> None:
        self.gpt = gpt

    def ingest_text(self, profile: HobbyProfile, text: str) -> Dict[str, float]:
        profile.raw_signals.append(text)
        low = text.lower()
        hits: Dict[str, float] = {}
        for axis, rules in _AXIS_RULES.items():
            vals = [v for kw, v in rules if kw in low]
            if vals:
                hits[axis] = sum(vals) / len(vals)
        if any(k in low for k in _BURNOUT_RULES):
            profile.burnout = min(1.0, profile.burnout + 0.4)
            hits.setdefault("energy", 0.1)
        for axis, val in hits.items():
            profile.set_axis(axis, val, conf=0.35)
        return hits

    def ingest_choice(self, profile: HobbyProfile, axis: str, option_index: int, n_options: int) -> None:
        if axis not in HOBBY_AXES or n_options < 2:
            return
        value = option_index / (n_options - 1)
        profile.set_axis(axis, value, conf=0.9)
        if axis == "energy" and value <= 0.0:
            profile.burnout = min(1.0, profile.burnout + 0.3)

    def ingest_choice_multi(self, profile: HobbyProfile, axis: str,
                            indices: List[int], n_options: int) -> None:
        """복수선택: 고른 보기들의 위치(0~1)를 평균 내어 축값으로 반영.
        넓게 고를수록 확신(conf)을 약간 낮춘다."""
        if axis not in HOBBY_AXES or n_options < 2:
            return
        idxs = [i for i in indices if 0 <= i < n_options]
        if not idxs:
            return
        vals = [i / (n_options - 1) for i in idxs]
        value = sum(vals) / len(vals)
        conf = 0.9 if len(idxs) == 1 else max(0.55, 0.9 - 0.12 * (len(idxs) - 1))
        profile.set_axis(axis, value, conf=conf)
        if axis == "energy" and value <= 0.0:
            profile.burnout = min(1.0, profile.burnout + 0.3)

    def ingest_passive(self, profile: HobbyProfile, signals: Dict[str, Any]) -> None:
        for axis, val in (signals or {}).items():
            if axis in HOBBY_AXES:
                profile.set_axis(axis, float(val), conf=0.5)


# ──────────────────────────────────────────────────────────────────────────────
# 6. 자기개선 랭커
# ──────────────────────────────────────────────────────────────────────────────
REASON_TO_AXIS: Dict[str, Tuple[str, float]] = {
    "too_active":   ("activity", 0.0), "too_calm":     ("activity", 1.0),
    "too_expensive":("budget", 0.0),   "too_social":   ("social", 0.0),
    "too_lonely":   ("social", 1.0),   "too_long":     ("time", 0.0),
    "too_hard":     ("achievement", 0.0), "not_new":    ("novelty", 1.0),
    "too_new":      ("novelty", 0.0),
}
REASON_LABEL = {
    "too_active": "너무 활동적이에요", "too_calm": "너무 정적이에요",
    "too_expensive": "비용이 부담돼요", "too_social": "혼자가 좋아요",
    "too_lonely": "사람들과 함께였으면", "too_long": "시간이 너무 들어요",
    "too_hard": "너무 어려워요", "not_new": "더 새로운 걸 원해요", "too_new": "익숙한 게 좋아요",
}


@dataclass
class SelfImprovingRanker:
    global_reward: Dict[str, float] = field(default_factory=dict)
    epsilon: float = 0.15

    def score(self, profile: HobbyProfile, hobby: Hobby) -> Tuple[float, float, float]:
        pv = [profile.axis.get(k, 0.5) for k in AXIS_KEYS]
        hv = hobby.vector()
        w = [profile.axis_weight.get(k, 1.0) for k in AXIS_KEYS]
        pw = [p * wi for p, wi in zip(pv, w)]
        hw = [h * wi for h, wi in zip(hv, w)]
        content = _cosine(pw, hw)
        greward = self.global_reward.get(hobby.id, 0.0)
        return content + 0.1 * greward, content, greward

    def recommend(self, profile: HobbyProfile, catalog: List[Hobby],
                  top_k: int = 3, explore: bool = True) -> List[Tuple[Hobby, float, float]]:
        scored = []
        for h in catalog:
            if h.id in profile.tried:
                continue
            total, content, _ = self.score(profile, h)
            if profile.burnout >= 0.6 and h.axis.get("activity", 0.5) > 0.6:
                total *= 0.4
            scored.append((h, total, content))
        scored.sort(key=lambda t: t[1], reverse=True)
        if not scored:
            return []
        result = scored[:top_k]
        if explore and len(scored) > top_k and random.random() < self.epsilon:
            wild = random.choice(scored[top_k:])
            result = result[:-1] + [wild]
        return result

    def apply_feedback(self, profile: HobbyProfile, hobby: Hobby,
                       kind: str, reason: Optional[str] = None) -> str:
        note = ""
        if kind == "dislike":
            if reason in REASON_TO_AXIS:
                axis, target = REASON_TO_AXIS[reason]
                profile.axis_weight[axis] = max(0.3, profile.axis_weight.get(axis, 1.0) * 0.7)
                cur = profile.axis.get(axis, 0.5)
                profile.set_axis(axis, cur + (target - cur) * 0.5, conf=0.6)
                note = f"'{REASON_LABEL.get(reason, reason)}' → '{HOBBY_AXES[axis][1]}' 축을 낮춰 다시 정렬했어요."
            else:
                note = "알겠어요. 비슷한 결의 추천을 줄일게요."
            self.global_reward[hobby.id] = self.global_reward.get(hobby.id, 0.0) - 0.5
        elif kind in ("like", "adopt", "save"):
            for k in AXIS_KEYS:
                cur = profile.axis.get(k, 0.5)
                profile.set_axis(k, cur + (hobby.axis.get(k, 0.5) - cur) * 0.25, conf=0.5)
            self.global_reward[hobby.id] = self.global_reward.get(hobby.id, 0.0) + (
                1.0 if kind == "adopt" else 0.6 if kind == "save" else 0.4)
            note = "좋아요 반영! 이런 결의 취미를 더 위로 올릴게요."
        elif kind == "tried":
            profile.tried.add(hobby.id)
            note = "이미 해본 취미로 표시하고 후보에서 제외했어요."
        elif kind == "dwell":
            self.global_reward[hobby.id] = self.global_reward.get(hobby.id, 0.0) + 0.1
        return note


# ──────────────────────────────────────────────────────────────────────────────
# 7. 안전/윤리 가드
# ──────────────────────────────────────────────────────────────────────────────
_CRISIS_PATTERNS = ["죽고", "자살", "살기 싫", "사라지고 싶", "해치고 싶"]


class SafetyGuard:
    DISCLAIMER = "※ 번아웃·감정 측정은 오늘의 컨디션 자가 참고일 뿐 의학적 진단이 아닙니다."

    @staticmethod
    def check_crisis(text: str) -> Optional[str]:
        low = (text or "").lower()
        if any(p in low for p in _CRISIS_PATTERNS):
            return ("마음이 많이 힘드신 것 같아 걱정돼요. 지금 느끼는 감정은 혼자 견디지 않으셔도 됩니다. "
                    "한국에서는 자살예방상담 109(24시간), 정신건강상담 1577-0199로 연락하면 "
                    "전문 상담을 받을 수 있어요. 취미 이야기는 마음이 좀 편해진 다음에 천천히 이어가요.")
        return None

    @staticmethod
    def soften_for_burnout(profile: HobbyProfile, text: str) -> str:
        if profile.burnout >= 0.6:
            return text + "\n\n오늘은 무리하지 않아도 괜찮아요. 회복이 먼저예요. " + SafetyGuard.DISCLAIMER
        return text


# ──────────────────────────────────────────────────────────────────────────────
# 8. 결과물 — 취미 DNA 리포트 (설명은 GPT가 동적으로 작성)
# ──────────────────────────────────────────────────────────────────────────────
class DNAReportBuilder:
    @staticmethod
    def explain(profile: HobbyProfile, hobby: Hobby, gpt: Optional[GPTBackend] = None) -> str:
        """추천 근거 1줄. online이면 GPT가 사용자 좌표를 분석해 문장 생성, 아니면 템플릿."""
        if gpt and gpt.online:
            coord = {HOBBY_AXES[k][1] if profile.axis.get(k, 0.5) >= 0.5 else HOBBY_AXES[k][0]:
                     round(profile.axis.get(k, 0.5), 2) for k in CORE_AXES if k in profile.axis}
            sys = ("너는 따뜻한 취미 코치다. 사용자의 성향 좌표와 추천된 취미를 보고, "
                   "'왜 이 사람에게 이 취미가 맞는지' 근거를 한 문장(존댓말, 40자 내외)으로 설명한다. "
                   "수치·전문용어 금지, 공감 어조.")
            usr = f"사용자 성향: {coord}\n추천 취미: {hobby.name} (태그: {', '.join(hobby.tags)})"
            txt = gpt.complete(sys, usr, temperature=0.6)
            if txt:
                return txt.strip().strip('"')
        diffs = sorted(AXIS_KEYS, key=lambda k: abs(profile.axis.get(k, 0.5) - hobby.axis.get(k, 0.5)))
        phrases = []
        for k in diffs[:2]:
            v = profile.axis.get(k, 0.5)
            phrases.append(HOBBY_AXES[k][1] if v >= 0.5 else HOBBY_AXES[k][0])
        return f"당신은 '{phrases[0]}·{phrases[1]}' 성향이라 → {hobby.name}을(를) 골랐어요."

    @staticmethod
    def coordinate_summary(profile: HobbyProfile) -> str:
        lines = []
        for k in CORE_AXES:
            v = profile.axis.get(k)
            if v is None:
                continue
            left, right = HOBBY_AXES[k]
            pos = int(round(v * 10))
            bar = "─" * pos + "●" + "─" * (10 - pos)
            lines.append(f"  {left:<12}{bar}{right:>12}")
        return "\n".join(lines)

    @staticmethod
    def stats(profile: HobbyProfile) -> List[Dict[str, str]]:
        """Stitch 상단 3카드(에너지/사회성/성취)용 요약 라벨."""
        a = profile.axis
        e = a.get("energy", 0.5)
        energy_label = "회복형" if e < 0.4 else ("균형형" if e <= 0.6 else "발산형")
        s = a.get("social", 0.5)
        social_label = (f"혼자 {round((1 - s) * 100)}%" if s < 0.5
                        else f"함께 {round(s * 100)}%")
        ach = a.get("achievement", a.get("motivation", 0.5))
        ach_label = "과정·기록" if ach < 0.5 else "결과·완성"
        return [{"label": "에너지", "value": energy_label},
                {"label": "사회성", "value": social_label},
                {"label": "성취", "value": ach_label}]

    @staticmethod
    def persona(profile: HobbyProfile, gpt: Optional[GPTBackend] = None) -> str:
        """한 줄 페르소나 라벨(예: '조용한 회복형 창작러')."""
        a = profile.axis
        if gpt and gpt.online:
            coord = {HOBBY_AXES[k][1] if a.get(k, 0.5) >= 0.5 else HOBBY_AXES[k][0]:
                     round(a.get(k, 0.5), 2) for k in CORE_AXES if k in a}
            sys = ("너는 취미 코치다. 사용자의 성향을 한국어 '한 줄 별명'으로 표현한다. "
                   "형식: '수식어 + 유형 + ~러/~형'(예: 조용한 회복형 창작러). "
                   "8~14자, 따옴표·문장부호 없이 별명만 출력.")
            txt = gpt.complete(sys, f"성향 좌표: {coord}", temperature=0.7)
            if txt:
                return txt.strip().strip('"').strip("'").split("\n")[0][:20]
        quiet = "조용한" if a.get("activity", 0.5) < 0.45 else "활기찬"
        e = a.get("energy", 0.5)
        etype = "회복형" if e < 0.45 else ("균형형" if e <= 0.6 else "발산형")
        if a.get("motivation", 0.5) >= 0.55:
            suffix = "창작러"
        elif a.get("novelty", 0.5) >= 0.6:
            suffix = "탐험러"
        else:
            suffix = "힐링러"
        return f"{quiet} {etype} {suffix}"

    @staticmethod
    def summary(profile: HobbyProfile, gpt: Optional[GPTBackend] = None) -> str:
        """'왜 이렇게 봤나요?' 본문(전체 근거 2문장)."""
        a = profile.axis
        if gpt and gpt.online:
            coord = {HOBBY_AXES[k][1] if a.get(k, 0.5) >= 0.5 else HOBBY_AXES[k][0]:
                     round(a.get(k, 0.5), 2) for k in CORE_AXES if k in a}
            sys = ("너는 따뜻한 취미 코치다. 사용자의 성향 좌표를 보고 '지금 이런 상태라 "
                   "이런 결의 취미를 골랐어요'를 2문장(존댓말, 80자 내외, 수치 금지)으로 설명한다.")
            txt = gpt.complete(sys, f"성향 좌표: {coord}", temperature=0.6)
            if txt:
                return txt.strip().strip('"')
        parts = []
        if a.get("energy", 0.5) < 0.45:
            parts.append("지금은 에너지 회복이 필요하고")
        else:
            parts.append("지금은 에너지가 차 있는 편이고")
        parts.append("혼자 손으로 사부작거릴 때 몰입이 높았어요" if a.get("social", 0.5) < 0.5
                     else "사람들과 함께할 때 활력이 올랐어요")
        tail = ("그래서 저강도·과정형 취미를 골랐어요." if a.get("activity", 0.5) < 0.5
                else "그래서 몸을 쓰는 발산형 취미를 골랐어요.")
        return " ".join(parts) + ". " + tail

    @classmethod
    def build(cls, profile: HobbyProfile, recs: List[Tuple[Hobby, float, float]],
              gpt: Optional[GPTBackend] = None) -> Dict[str, Any]:
        items = []
        for h, total, content in recs:
            cat = HOBBY_CATEGORY.get(h.id, "creative")
            items.append({
                "id": h.id, "name": h.name, "fit": round(content * 100),
                "why": cls.explain(profile, h, gpt), "first_spark": h.first_spark,
                "cost": h.cost_per_month, "equipment": h.equipment,
                "difficulty": h.difficulty, "time": h.time_needed, "daynight": h.daynight,
                "emoji": getattr(h, "emoji", None) or HOBBY_EMOJI.get(h.id, "🎯"),
                "tags": (h.tags or [])[:3],
                "category_label": CATEGORY_LABEL.get(cat, "취미"),
                "custom": bool(getattr(h, "custom", False)),
            })
        return {"coordinate": cls.coordinate_summary(profile),
                "profile": profile.to_dict(), "items": items,
                "persona": cls.persona(profile, gpt),
                "summary": cls.summary(profile, gpt),
                "stats": cls.stats(profile),
                "disclaimer": SafetyGuard.DISCLAIMER}

    @staticmethod
    def render_text(report: Dict[str, Any]) -> str:
        out = ["🧬 당신의 취미 DNA 리포트", "=" * 44, "[지금의 나 — 성향 좌표]",
               report["coordinate"], "", "[딱 맞는 취미 처방]"]
        for i, it in enumerate(report["items"], 1):
            out += [f"\n{i}. {it['name']}   (적합도 {it['fit']}%)",
                    f"   💡 왜? {it['why']}", f"   🔥 첫 불씨: {it['first_spark']}",
                    f"   💰 {it['cost']} · 🎒 {it['equipment']} · ⏱ {it['time']} · "
                    f"🌗 {it['daynight']} · 난이도 {it['difficulty']}"]
        out += ["", report["disclaimer"]]
        return "\n".join(out)


def explain_hobby(meta: Dict[str, Any], profile_axis: Optional[Dict[str, float]],
                  gpt: Optional["GPTBackend"] = None) -> Dict[str, Any]:
    """선택한 취미를 '사용자 성향에 맞춰' 소개. online이면 GPT가 개인화 생성, 아니면 템플릿.
    반환: {intro, fit_line, steps[3], tips[2~3], budget}"""
    name = meta.get("name", "이 취미")
    tags = meta.get("tags", [])
    cost = meta.get("cost", "미정")
    equip = meta.get("equipment", "간단한 준비물")
    ttime = meta.get("time", "30분~")
    diff = meta.get("difficulty", "보통")
    spark = meta.get("first_spark", "오늘 10분만 가볍게 시작해보기.")
    if gpt and getattr(gpt, "online", False):
        axis_txt = {}
        if profile_axis:
            axis_txt = {HOBBY_AXES[k][1] if profile_axis.get(k, 0.5) >= 0.5 else HOBBY_AXES[k][0]:
                        round(profile_axis.get(k, 0.5), 2) for k in CORE_AXES if k in profile_axis}
        sys = ("너는 따뜻한 취미 코치다. 주어진 취미를 사용자에게 맞춰 소개하고, 오직 JSON만 출력한다. "
               "키: intro(2~3문장, 이 취미가 어떤 취미인지+분위기), "
               "fit_line(사용자 성향에 왜 맞는지 한 문장. 성향 정보 없으면 일반적 매력 한 문장), "
               "steps(초심자 시작 3단계, 각 한 문장 배열), "
               "tips(알아두면 좋은 점/주의 2~3개 배열), budget(예상 비용/투자 한 줄). "
               "존댓말, 수치 과장·의학적 단정 금지.")
        usr = (f"취미: {name} (태그 {', '.join(tags)}, 비용 {cost}, 장비 {equip}, "
               f"1회 {ttime}, 난이도 {diff})\n사용자 성향: {axis_txt or '정보 없음'}")
        raw = gpt.complete(sys, usr, temperature=0.6)
        if raw:
            try:
                s = raw.strip()
                if s.startswith("```"):
                    s = s.split("```")[1].replace("json", "", 1).strip()
                data = json.loads(s)
                data.setdefault("budget", cost)
                if isinstance(data.get("steps"), list) and isinstance(data.get("tips"), list):
                    return data
            except Exception:
                pass
    # 오프라인/파싱 실패 폴백
    tag0 = tags[0] if tags else "새로운"
    return {
        "intro": f"{name}은(는) {tag0} 결의 취미예요. 부담 없이 시작해 나만의 속도로 즐기기 좋아요.",
        "fit_line": ("지금의 컨디션과 성향에 무리 없이 어울리는 활동이에요."
                     if profile_axis else "처음 시작하기에도 진입장벽이 낮은 편이에요."),
        "steps": ["가볍게 관련 정보와 예시를 5분만 찾아보기.",
                  spark,
                  "일주일에 한 번, 짧게라도 반복해 습관의 씨앗 만들기."],
        "tips": [f"필요한 준비물: {equip}.", f"난이도: {diff} · 1회 {ttime}.",
                 "완벽하게 하려 하지 말고 '오늘 한 번'에만 집중하세요."],
        "budget": cost,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 9. 도구 스펙 (GPT function calling)
# ──────────────────────────────────────────────────────────────────────────────
TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "ask_user",
        "description": ("사용자에게 '직접 분석해서 만든' 맞춤 선택지를 제시한다(질문선택 모드). "
                        "정해진 보기를 쓰지 말고, 직전 대화 맥락을 분석해 이 사람에게 가장 알맞은 "
                        "표현으로 '정확히 4개' 보기를 그 자리에서 생성한다. 사용자는 복수선택(중복)도 "
                        "할 수 있으니, 4개 보기는 서로 배타적이지 않아도 된다."),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "감성적이고 짧은 질문(문진표 톤 금지)"},
                "options": {"type": "array", "items": {"type": "string"},
                            "minItems": 4, "maxItems": 4,
                            "description": "맥락에 맞춘 보기 정확히 4개. 왼쪽 극→오른쪽 극 순서."},
                "axis_hint": {"type": "string", "enum": AXIS_KEYS,
                              "description": "이 질문이 수집하는 프로파일 축"},
            },
            "required": ["question", "options", "axis_hint"],
        },
    },
    {
        "name": "recommend_hobbies",
        "description": "현재까지 분석한 프로파일로 취미 후보를 추천한다(핵심 축이 어느 정도 모였을 때).",
        "parameters": {"type": "object", "properties": {"top_k": {"type": "integer", "default": 3}}},
    },
    {
        "name": "propose_hobbies",
        "description": ("내장 카탈로그에 없지만 사용자 성향에 더 잘 맞는 '새로운 취미'를 직접 제안한다. "
                        "사용자가 특정 관심사(예: 사진·글쓰기·게임)를 자유입력으로 언급했거나, "
                        "고정 목록이 부족하다고 판단될 때 1~3개를 창의적으로 만들어 추가한다. "
                        "추가 후 recommend_hobbies/finalize_report로 이어간다."),
        "parameters": {
            "type": "object",
            "properties": {
                "hobbies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "취미 이름(한국어)"},
                            "emoji": {"type": "string", "description": "대표 이모지 1개"},
                            "tags": {"type": "array", "items": {"type": "string"},
                                     "description": "특징 태그 2~3개"},
                            "cost": {"type": "string", "description": "월 예상 비용(예: '0~2만원/월')"},
                            "equipment": {"type": "string", "description": "필요 장비"},
                            "difficulty": {"type": "string", "description": "난이도"},
                            "time": {"type": "string", "description": "1회 소요 시간"},
                            "daynight": {"type": "string", "description": "적합 시간대"},
                            "first_spark": {"type": "string", "description": "오늘 당장 할 수 있는 첫 행동"},
                            "axis": {
                                "type": "object",
                                "description": "성향 좌표 추정(각 0~1). energy/social/activity/budget/time 최소 포함",
                                "properties": {k: {"type": "number"} for k in AXIS_KEYS},
                            },
                        },
                        "required": ["name", "tags", "cost", "first_spark", "axis"],
                    },
                },
            },
            "required": ["hobbies"],
        },
    },
    {
        "name": "give_feedback",
        "description": "사용자가 추천에 보인 반응을 학습에 반영한다(자기개선 루프).",
        "parameters": {
            "type": "object",
            "properties": {
                "hobby_id": {"type": "string"},
                "kind": {"type": "string", "enum": ["like", "dislike", "tried", "save", "adopt", "dwell"]},
                "reason": {"type": "string", "enum": list(REASON_TO_AXIS.keys()),
                           "description": "dislike일 때 어느 축이 틀렸는지 분석해 지정"},
            },
            "required": ["hobby_id", "kind"],
        },
    },
    {"name": "finalize_report",
     "description": "발굴을 마무리하고 취미 DNA 리포트(처방)를 생성한다.",
     "parameters": {"type": "object", "properties": {}}},
]

SYSTEM_PROMPT = """\
당신은 '하비DNA'의 취미 발굴 코치입니다. "취미가 없고 나도 날 잘 모르는" 사람을 따뜻하게 진단해
딱 맞는 취미를 발굴·설명·처방합니다. 클래스 예약/모임 매칭은 하지 않고 '발굴'만 극대화합니다.

[가장 중요 — 직접 판단해서 선택지를 만들 것]
- 고정된 설문지를 읽지 마세요. 사용자가 방금 한 말을 분석해서, 그 사람에게 가장 알맞은 질문과 보기를
  '그 자리에서' 만들어 ask_user로 제시하세요. (예: 사용자가 "퇴근하면 진이 빠져요"라고 하면 에너지 축을
  그 맥락의 표현으로 물어봅니다.)
- 보기는 '정확히 4개', 왼쪽 극→오른쪽 극 순서로. 문진표 말투 금지, "오늘 당신의 마음을 진단해 드려요" 톤.
- 한 번에 다 묻지 마세요(설문 피로). 가장 정보가 부족한 축부터 한 축씩.
- ★첫 인사 다음부터는 사용자가 '직접 타이핑하지 않고 보기를 눌러서' 답합니다. 그러니 자유 텍스트로만
  되묻지 말고, 반드시 ask_user(또는 추천·리포트) 도구를 호출하세요. 사용자는 보기를 복수선택할 수 있습니다.

[흐름]
1) 첫 자유응답을 분석한 뒤부터는 ask_user로 맞춤 4지선다를 제시합니다(자유 텍스트 되묻기 금지).
2) 정량 축(에너지·사회성·활동량·예산·시간)을 한 축씩 ask_user로 채웁니다.
3) 핵심 5축이 어느 정도 차면 recommend_hobbies로 추천하고, '왜 이 취미인지' 근거를 1줄로 답합니다.
   ★ 사용자가 자유입력(기타)으로 특정 관심사를 말하거나 내장 목록이 부족하면, propose_hobbies로
     목록 밖 취미를 직접 만들어 추가한 뒤 추천하세요(고정 10개에 갇히지 말 것).
   ★ 자유입력에는 먼저 공감/대화로 짧게 반응해도 됩니다(툴 없이 say 가능). 그 다음 질문이나 제안으로 이어가세요.
4) 사용자가 '별로예요/좋아요/이미 해봤어요'로 반응하면 give_feedback으로 즉시 학습합니다.
   '별로예요'면 어느 축이 틀렸는지 직접 분석해 reason을 정하세요.
5) 충분하면 finalize_report로 마무리합니다.

[안전] 번아웃·감정은 '오늘의 컨디션' 자가 참고일 뿐 진단이 아닙니다. 심한 소진·우울 신호엔 취미를
강권하지 말고 따뜻하게 전문가 상담을 함께 안내하세요.
"""


# ──────────────────────────────────────────────────────────────────────────────
# 10. 하이브리드 대화 에이전트
# ──────────────────────────────────────────────────────────────────────────────
class HybridConversationAgent:
    """대화형(자유응답) + 질문선택형(GPT가 동적 생성한 보기) 하이브리드 루프."""

    def __init__(self, user_id: str = "demo", ranker: Optional[SelfImprovingRanker] = None) -> None:
        self.gpt = GPTBackend()
        self.ingestor = SignalIngestor(self.gpt)
        self.ranker = ranker or SelfImprovingRanker()
        self.profile = HobbyProfile(user_id=user_id)
        self.catalog = list(HOBBY_CATALOG)  # 세션별 복사(커스텀 취미가 전역 오염 방지)
        self.history: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.last_recs: List[Tuple[Hobby, float, float]] = []
        self._pending_axis: Optional[str] = None
        self.turns: int = 0  # 사용자 발화 횟수(첫 자유응답=1)
        self._custom_n: int = 0
        self._force: str = "auto"  # 이번 턴 tool_choice

    def send(self, user_text: str, choice_index: Optional[int] = None,
             choice_indices: Optional[List[int]] = None,
             n_options: Optional[int] = None) -> Dict[str, Any]:
        crisis = SafetyGuard.check_crisis(user_text)
        if crisis:
            return {"type": "say", "text": crisis}
        self.turns += 1
        if self._pending_axis and n_options:
            if choice_indices:
                self.ingestor.ingest_choice_multi(self.profile, self._pending_axis,
                                                  choice_indices, n_options)
                self._pending_axis = None
            elif choice_index is not None:
                self.ingestor.ingest_choice(self.profile, self._pending_axis,
                                            choice_index, n_options)
                self._pending_axis = None
        is_choice = choice_index is not None or bool(choice_indices)
        if user_text and not is_choice:
            self.ingestor.ingest_text(self.profile, user_text)
        # tool_choice 분기: 첫 응답·선택 = 구조적 진행(required), 자유입력(기타) = 대화 허용(auto)
        if self.turns == 1 or is_choice:
            self._force = "required"
        else:
            self._force = "auto"
        self.history.append({"role": "user", "content": user_text or "(선택)"})
        return self._run_tool_loop()

    def _run_tool_loop(self) -> Dict[str, Any]:
        steps = 0
        while steps < 6:
            steps += 1
            ctx = (f"[상태] 핵심축 완성도={round(self.profile.completeness()*100)}%, "
                   f"미수집축={self.profile.missing_core()}, 번아웃={round(self.profile.burnout,2)}, "
                   f"추천이력={'있음' if self.last_recs else '없음'}")
            msgs = self.history + [{"role": "system", "content": ctx}]
            # 선택/첫응답은 required(구조적 진행), 자유입력은 auto(대화 허용).
            # 단, 루프 2회차부터는 도구 호출을 유도(무한 say 방지).
            force = self._force if steps == 1 else "required"
            resp = self.gpt.chat(msgs, TOOL_SPECS, tool_choice=force)

            if not resp["tool_calls"]:
                text = SafetyGuard.soften_for_burnout(self.profile, resp["text"] or "조금 더 들려주세요.")
                self.history.append({"role": "assistant", "content": text})
                return {"type": "say", "text": text}

            call = resp["tool_calls"][0]
            name, args = call["name"], call["arguments"]

            if name == "ask_user":
                self._pending_axis = args.get("axis_hint")
                self.history.append({"role": "assistant", "content": f"(질문) {args.get('question','')}"})
                return {"type": "ask", "text": args.get("question", ""),
                        "options": args.get("options", []), "axis": self._pending_axis}

            if name == "recommend_hobbies":
                self.last_recs = self.ranker.recommend(self.profile, self.catalog,
                                                       top_k=int(args.get("top_k", 3)))
                lines = [f"{h.id}: {h.name} — {DNAReportBuilder.explain(self.profile, h, self.gpt)}"
                         for h, _, _ in self.last_recs]
                self.history.append({"role": "system",
                                     "content": "recommend_done\n추천결과:\n" + "\n".join(lines)})
                continue

            if name == "propose_hobbies":
                added = self._add_custom_hobbies(args.get("hobbies", []))
                self.history.append({"role": "system",
                                     "content": f"propose_done\n추가된 취미: {added}"})
                continue

            if name == "give_feedback":
                hobby = next((h for h in self.catalog if h.id == args.get("hobby_id")), None)
                if hobby:
                    note = self.ranker.apply_feedback(self.profile, hobby,
                                                      args.get("kind", ""), args.get("reason"))
                    self.last_recs = self.ranker.recommend(self.profile, self.catalog, top_k=3)
                    self.history.append({"role": "system",
                                         "content": f"피드백 반영: {note}\n재추천 완료."})
                    continue

            if name == "finalize_report":
                if not self.last_recs:
                    self.last_recs = self.ranker.recommend(self.profile, self.catalog, top_k=4)
                report = DNAReportBuilder.build(self.profile, self.last_recs, self.gpt)
                self.history.append({"role": "assistant", "content": "(리포트 생성 완료)"})
                return {"type": "report", "report": report,
                        "text": DNAReportBuilder.render_text(report)}

        return {"type": "say", "text": "조금 더 이야기해 주실래요?"}

    def _add_custom_hobbies(self, hobbies: List[Dict[str, Any]]) -> List[str]:
        """GPT가 제안한 목록 밖 취미를 세션 카탈로그에 병합."""
        added = []
        for hb in (hobbies or [])[:3]:
            if not hb.get("name"):
                continue
            self._custom_n += 1
            hid = f"gpt{self._custom_n}"
            axis = {k: float(hb.get("axis", {}).get(k, 0.5)) for k in AXIS_KEYS}
            h = Hobby(
                id=hid, name=hb["name"], tags=hb.get("tags", [])[:4] or ["새로움"],
                axis=axis, cost_per_month=hb.get("cost", "미정"),
                equipment=hb.get("equipment", "간단한 준비물"),
                difficulty=hb.get("difficulty", "보통"),
                time_needed=hb.get("time", "30분~"),
                daynight=hb.get("daynight", "언제든"),
                first_spark=hb.get("first_spark", "오늘 10분만 가볍게 시작해보기."),
            )
            setattr(h, "emoji", hb.get("emoji", "✨"))
            setattr(h, "custom", True)
            self.catalog.append(h)
            added.append(h.name)
        return added

    # 외부에서 직접 피드백 (선택지 버튼용)
    def feedback(self, hobby_id: str, kind: str, reason: Optional[str] = None) -> Dict[str, Any]:
        hobby = next((h for h in self.catalog if h.id == hobby_id), None)
        if not hobby:
            return {"type": "say", "text": "그 취미를 찾지 못했어요."}
        note = self.ranker.apply_feedback(self.profile, hobby, kind, reason)
        self.last_recs = self.ranker.recommend(self.profile, self.catalog, top_k=3)
        report = DNAReportBuilder.build(self.profile, self.last_recs, self.gpt)
        return {"type": "report", "note": note, "report": report,
                "text": DNAReportBuilder.render_text(report)}


# ──────────────────────────────────────────────────────────────────────────────
# 11. 오프라인 데모
# ──────────────────────────────────────────────────────────────────────────────
def _demo() -> None:
    random.seed(7)
    agent = HybridConversationAgent("demo")
    print("LLM:", "GPT-online" if agent.gpt.online else "오프라인 스텁")
    out = agent.send("요즘 회사 일로 완전 번아웃이라 뭐든 시작할 에너지가 없어요.")
    auto = [0, 0, 0, 0, 0]
    ci = 0
    for _ in range(14):
        if out["type"] == "ask":
            print("\n🤖", out["text"])
            for i, o in enumerate(out["options"]):
                print(f"   [{i}] {o}")
            idx = auto[ci] if ci < len(auto) else 0
            ci += 1
            print("👤", out["options"][idx])
            out = agent.send(out["options"][idx], choice_index=idx, n_options=len(out["options"]))
        elif out["type"] == "report":
            print("\n" + out["text"])
            break
        else:
            print("\n🤖", out["text"])
            out = agent.send("리포트로 정리해줘")


if __name__ == "__main__":
    _demo()
