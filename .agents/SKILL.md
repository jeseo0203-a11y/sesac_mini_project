---
name: hobby-road-engine
description: Provides project rules for building the "취미로(HobbyRoad)" personalized hobby recommendation AI service — persona/tone guardrails, JSON output schema, hard-filter and fallback logic, RIASEC mapping, and tech stack conventions. Use this skill whenever writing or editing code related to the recommendation pipeline, survey-to-profile mapping, hobby_profile dataset, LLM prompts (emotional state / candidate selection), risk_flag safety branch, or pyproject.toml dependencies for this project.
---

# 취미로(HobbyRoad) 추천 엔진 개발 스킬

이 스킬은 초개인화 취미 추천 AI 서비스 "취미로"의 PRD·데이터셋·검증 결과를 기반으로 한다.
코드를 작성하기 전에 이 문서의 규칙을 먼저 따르고, 규칙과 다른 판단이 필요하면 임의로 결정하지 말고 사용자에게 먼저 확인한다.

## 1. 서비스 페르소나 & 절대 금지 사항

- 말투: 따뜻하고 공감하는 "취미 처방사" 톤. 나이·성별 무관하게 편안함.
- **절대 금지 단어**: "진단", "점수", "장애", "우울증" 등 의학적 표현. 대신 "오늘의 컨디션", "에너지 상태", "회복 필요도"로만 표기.
- 첫걸음 행동(beginner_action)은 **5~10분 내 실행 가능한 것만**. 예약/결제/가입 등 고관여 행동 제안 금지.
- 랭킹 스코어 산식·전역 학습·협업 필터링·자체 ML 학습은 이 MVP에서 사용하지 않는다. 후보를 "해석해서 선별·설명·처방"하는 구조를 유지한다.
- 로직 변경은 최대한 코드가 아니라 **프롬프트 또는 데이터 시트(hobby_profile) 수정**으로 처리할 수 있게 설계한다(비전공자 팔로우업 고려).

## 2. 안전 분기 (risk_flag) — 최우선 규칙

자유입력·대화에서 자해/극단적 무기력 신호가 감지되면:
1. `emotional_state = "risk"`, `risk_flag = true`로 산출
2. 이후 파이프라인(후보검색 ③ → 선별·설명 ④ → RAG보강 ⑤)을 **즉시 중단**한다 — 어떤 상황에서도 예외 없음
3. 아래 고정 문구를 `support_message`로 반환한다(변형 금지):
   `"당신의 마음을 들어줄 전문가들이 늘 기다리고 있습니다. 정신건강상담전화 [109] 또는 보건복지상담센터 [129]로 연락해 보세요."`

## 3. LLM 출력 JSON 스키마 (고정)

```json
// 케이스 A: 정상 상태
{
  "user_status": {"emotional_state": "burnout_type | boreout_type | steady", "empathy_message": "string"},
  "recommendations": [
    {"hobby_id": "string(데이터셋 그대로)", "hobby_name": "string(데이터셋 그대로)", "reason_clause": "string", "recommendation_type": "안정 | 의외 | 회복 | 관계"}
  ],
  "beginner_action": "string",
  "risk_flag": false,
  "support_message": ""
}
// 케이스 B: risk 상태 — recommendations는 반드시 빈 배열, beginner_action은 빈 문자열
{
  "user_status": {"emotional_state": "risk", "empathy_message": "string"},
  "recommendations": [],
  "beginner_action": "",
  "risk_flag": true,
  "support_message": "당신의 마음을 들어줄 전문가들이 늘 기다리고 있습니다. 정신건강상담전화 [109] 또는 보건복지상담센터 [129]로 연락해 보세요."
}
```
- 반드시 유효한 단일 JSON 객체만 반환. 마크다운 코드블록·후행 쉼표 금지.
- `hobby_id`/`hobby_name`은 hobby_profile 데이터셋에 존재하는 값만 사용(존재하지 않는 취미 생성 금지 — 할루시네이션 방지 핵심 규칙).

## 4. hobby_profile 데이터셋 필드명 (한글 필드 그대로 사용)

`hobby_profile_dataset_v1.json`의 실제 키는 한글이다. 영문으로 임의 변환하지 말고 아래 키를 그대로 참조한다:

```
hobby_id, 취미명, riasec_code, 초기비용, 지속비용, 세션당시간, 공간, 사회성, 강도,
학습곡선, 성취방식, 감각태그, 신규성, beginner_action(첫행동), 준비물,
safety_notes(안전), 외부시작경로, RAG설명(임베딩본문), RAG검색키워드,
is_synthetic, 비용검증상태, 안전검증상태, fallback_set
```

값 도메인(실측):
- 초기비용: 무료 / 1만원 이하 / 3만원 이하 / 3만원 이상
- 세션당시간: 5분 / 15분 / 30분 / 1시간 이상
- 사회성: 완전 개인 / 온라인 느슨한 연결 / 오프라인 소규모 (※ "오프라인 대규모"는 현재 데이터 0건)
- 강도: 정적 / 저강도 / 중강도 이상 (※ "중강도 이상"은 현재 1건뿐 — 활동적 사용자는 후보 부족 위험)

## 5. 설문(9축) → 취미필드 하드필터 매핑 규칙

예산·사회성·활동량·시간(가용시간대) 4축은 **하드 제약**으로 필터링한다(FR-407-1: 의외 추천도 이 하드 제약은 반드시 지킴).

```python
BUDGET_CEIL = {
  'budget_0':   ['무료'],
  'budget_low': ['무료','1만원 이하'],
  'budget_mid': ['무료','1만원 이하','3만원 이하'],   # 3~5만원 옵션이지만 데이터 상한은 '3만원 이하'로 보수적 매핑(4~5만원 구간은 데이터 보강 전까지 미확정)
  'budget_high':['무료','1만원 이하','3만원 이하','3만원 이상'],
}
SOCIALITY = {
  'solo_strong': ['완전 개인'],
  'solo_mild':   ['완전 개인','온라인 느슨한 연결'],
  'flexible':    ['완전 개인','온라인 느슨한 연결','오프라인 소규모','오프라인 대규모'],
  'social_mild': ['온라인 느슨한 연결','오프라인 소규모'],
  'social_strong':['오프라인 소규모','오프라인 대규모'],
}
ACTIVITY = {
  'static':  ['정적'],
  'light':   ['정적','저강도'],
  'moderate':['저강도','중강도 이상'],
  'intense': ['중강도 이상'],
}
```
- `budget_0` 선택 시 지속비용='정기결제'인 취미는 함께 제외한다.
- 크로노타입 `night_owl` + 가용시간대 `weekday_evening` 조합이면 공간='외출 필요' 취미는 제외한다.

## 6. [필수] 설문에 세션시간 축 추가

기존 9축 설문에는 1회 세션 소요시간 문항이 없다. 1단계 핵심 문항에 아래를 반드시 추가한다:

- 질문: "한 번에 이 정도면 좋아요"
- 옵션: 5~10분 / 15~30분 / 1시간 이상 무관 / 즉흥적으로(제한없음)
- `hobby_profile.세션당시간`과 직접 매칭하는 **하드 상한 필터**로 적용한다.
- 에너지축에서 `burnout_severe`(최하 컨디션) 선택 시, 사용자가 세션시간을 별도 선택하지 않아도 서버 기본값을 '15~30분'으로 강제 적용한다.

## 7. [필수] 모순 케이스(US-1) 완화 규칙

활동강도='정적' AND 사회성 선호>=`social_mild` 조합이 감지되면(FR-302 모순 플래그) 그대로 하드필터를 적용하지 않는다. 오프라인 소규모 취미가 전부 강도 '저강도' 이상이라 완전히 걸러지기 때문이다.

```
IF 모순_flag == True:
    강도 필터를 'static' → 'static + light' 로 1단계만 완화 (예산·시간·공간 등 다른 하드제약은 유지)
    카드 근거문장에 "저강도로 참여 가능한" 문구를 명시
```

## 8. [필수] 후보 부족 시 완화 체인

```
IF 하드필터 통과 후보 수 < 3:
    1) 가장 최근에 적용한 제약(활동량 또는 사회성)부터 1단계씩 완화
    2) 그래도 3 미만이면 RIASEC 코드 매칭만으로 완화 검색
    3) 완화된 카드에는 "선호와 100% 일치하진 않지만" 톤의 안내 문구 삽입
```
외부 LLM/임베딩 API 자체가 장애일 때는 이 규칙 대신 `fallback_정적세트`(RIASEC 유형별 대표 취미, 시트에 고정)를 사용한다.

## 9. [필수] 카드 배분 우선순위 (안정 vs 의외 충돌 시)

의외 추천은 "항상 1개" 노출이 서비스 정체성이므로 최우선이다. 후보가 적어 안정 카드와 충돌하면:

```
1순위: 의외 카드 1개 확보 (협상 불가)
2순위: 남은 후보로 안정 카드, 최소 2개까지는 확보
3순위: 안정 카드가 2개 미만이면 §8 완화 체인을 먼저 적용 후 재배분
```
의외 추천도 §5의 하드 제약(예산·시간·공간)은 반드시 지킨다 — "취향(RIASEC·감각·신규성) 차원에서만" 의외성을 부여한다.

## 10. RIASEC 추론은 고정 매핑표로만 — LLM 자유 추론 금지

9축 설문은 RIASEC을 직접 묻지 않는다. LLM이 매번 다르게 추론하면 "의외"의 기준이 세션마다 흔들리므로, 아래처럼 **규칙 기반으로 고정**한다(코드 또는 시트로 관리, 프롬프트에는 "아래 표 기준으로만 판단, 자유 추론 금지" 명시):

```
동기(motive_creation) → A +1
동기(motive_growth) → I, E +1
동기(motive_relationship) → S +1
성취방식(outcome_product) → R, A +1
성취방식(outcome_process) → I, C +1
(전체 매핑표는 별도 관리 시트 참조)

의외 판정 = riasec_inferred 상위 2개 유형과 겹치지 않는 취미 우선
          + 신규성 선호가 '익숙'이면 신규성='새로움' 취미 가점
```

## 11. 기술 스택 / pyproject.toml (확정본)

LangChain은 사용하지 않는다(RAG·LLM 호출 모두 직접 SDK 사용으로 확정). 계약서 분석 템플릿에서 유입된 `pymupdf`/`pdfplumber`/`python-multipart`는 사용 금지(파일 업로드 기능 없음).

```toml
python = ">=3.12,<3.13"
fastapi = "^0.111.0"
uvicorn = "^0.30.0"
python-dotenv = "^1.0.1"
openai = "^1.35.0"        # LLM 해석/선별/설명 생성 — OpenAI SDK 직접 호출
chromadb = "^0.5.0"       # 벡터 검색 — ChromaDB 클라이언트 직접 사용 (LangChain 래퍼 사용 안 함)
supabase = "^2.5.0"       # user_profile/hobby_profile/feedback_history/business_event
pydantic = "^2.7.0"
pydantic-settings = "^2.3.0"

[tool.poetry.group.dev.dependencies]
pandas = "^2.2.0"         # 구글시트→CSV→Supabase 적재 스크립트 전용, 런타임 미포함
```

## 12. 비용/안전 필드는 LLM이 생성하지 않는다

`초기비용`·`지속비용`·`safety_notes(안전)`는 데이터셋에 사람이 검증한 값만 사용한다. LLM이 임의로 가격이나 주의사항을 새로 생성하는 것은 금지 — 프롬프트에 명시적으로 차단 문구를 포함시킨다. 카드 비용 표기는 항상 "예상 범위이며 실제와 다를 수 있어요" 고지를 동반한다.
