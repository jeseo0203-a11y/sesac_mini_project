import os
import sys
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from supabase import create_client, Client

# .env 파일 로드
load_dotenv()

# API 키 및 환경 변수 취득
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

DATA_FILE_PATH = "data/hobby_profile_dataset_v1.json"
CHROMA_DB_PATH = "backend/chromadb_data"
COLLECTION_NAME = "hobby_profiles"

def load_and_sanitize_data(file_path: str):
    """JSON 파일을 로드하여 기획 보정 사항(is_synthetic=False, 검증상태=검증완료)을 반영합니다."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"데이터셋 파일을 찾을 수 없습니다: {file_path}")
        
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    raw_profiles = data.get("hobby_profile", [])
    sanitized_profiles = []
    
    for item in raw_profiles:
        # is_synthetic 불리언 변환 (JSON 문자열 "TRUE"/"FALSE" 대응)
        synthetic_str = str(item.get("is_synthetic", "FALSE")).upper()
        item["is_synthetic"] = True if synthetic_str == "TRUE" else False
        
        # 비용검증상태 및 안전검증상태 원본 보존
        item["비용검증상태"] = item.get("비용검증상태", "확인필요")
        item["안전검증상태"] = item.get("안전검증상태", "확인필요")
        
        # fallback_set 불리언 변환
        fallback_str = str(item.get("fallback_set", "FALSE")).upper()
        item["fallback_set"] = True if fallback_str == "TRUE" else False
        
        sanitized_profiles.append(item)
        
    print(f"총 {len(sanitized_profiles)}개의 취미 데이터를 성공적으로 로드 및 보정했습니다.")
    return sanitized_profiles

def get_openai_embeddings(text: str, client: OpenAI) -> list:
    """OpenAI API를 사용하여 text-embedding-3-small 모델로 임베딩을 생성합니다."""
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def seed_chromadb(profiles: list, openai_client: OpenAI, dummy: bool = False):
    """ChromaDB 로컬 데이터 저장소에 임베딩 및 메타데이터를 적재합니다."""
    print("ChromaDB 적재를 시작합니다...")
    if dummy:
        print("⚠️ 더미 모드 활성화: OpenAI API 호출 없이 더미 임베딩([0.0]*1536)을 생성하여 적재합니다.")
        
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    
    # 컬렉션 생성 (기존 컬렉션이 있으면 삭제 후 재생성하여 중복 방지)
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        print(f"기존 ChromaDB 컬렉션 '{COLLECTION_NAME}'을 삭제했습니다.")
    except Exception:
        pass
        
    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"} # 코사인 유사도 사용
    )
    
    ids = []
    documents = []
    embeddings = []
    metadatas = []
    
    for idx, item in enumerate(profiles):
        hobby_id = item["hobby_id"]
        hobby_name = item["취미명"]
        rag_desc = item.get("RAG설명(임베딩본문)", "")
        
        if not rag_desc:
            print(f"⚠️ 경고: {hobby_name}({hobby_id})에 RAG 설명이 비어 있습니다. 임베딩 적재를 생략합니다.")
            continue
            
        if dummy:
            vector = [0.0] * 1536
        else:
            print(f"[{idx+1}/{len(profiles)}] '{hobby_name}' 임베딩 생성 중...")
            vector = get_openai_embeddings(rag_desc, openai_client)
        
        # 메타데이터 구성 (하드필터에 쓰일 핵심 속성들을 메타데이터로 함께 저장)
        metadata = {
            "hobby_id": hobby_id,
            "hobby_name": hobby_name,
            "riasec_code": item.get("riasec_code", ""),
            "initial_cost": item.get("초기비용", ""),
            "ongoing_cost": item.get("지속비용", ""),
            "session_time": item.get("세션당시간", ""),
            "space_type": item.get("공간", ""),
            "social_type": item.get("사회성", ""),
            "intensity_level": item.get("강도", ""),
            "novelty_level": item.get("신규성", ""),
            "fallback_set": item.get("fallback_set", False)
        }
        
        ids.append(hobby_id)
        documents.append(rag_desc)
        embeddings.append(vector)
        metadatas.append(metadata)
        
    # ChromaDB에 일괄 삽입
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )
    print(f"ChromaDB 적재 완료! 총 {len(ids)}개의 아이템이 등록되었습니다.")

def seed_supabase(profiles: list):
    """Supabase RDB에 취미 마스터 데이터를 적재합니다."""
    if not SUPABASE_URL or not SUPABASE_KEY or "your-supabase" in SUPABASE_URL:
        print("⚠️ Supabase URL 또는 Key가 설정되지 않았거나 기본값 상태입니다.")
        print("Supabase 적재는 진행하지 않으며, SQL DDL 스크립트(backend/schema.sql)를 이용해 직접 테이블을 셋업해 주세요.")
        return

    print("Supabase RDB 적재를 시작합니다...")
    supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    db_data = []
    for item in profiles:
        # 한글 키명을 DB의 영문 컬럼명으로 매핑
        mapped_item = {
            "hobby_id": item["hobby_id"],
            "hobby_name": item["취미명"],
            "riasec_code": item["riasec_code"],
            "initial_cost": item.get("초기비용"),
            "ongoing_cost": item.get("지속비용"),
            "session_time": item.get("세션당시간"),
            "space_type": item.get("공간"),
            "social_type": item.get("사회성"),
            "intensity_level": item.get("강도"),
            "learning_curve": item.get("학습곡선"),
            "achievement_type": item.get("성취방식"),
            "sensory_tags": item.get("감각태그"),
            "novelty_level": item.get("신규성"),
            "beginner_action": item.get("beginner_action(첫행동)"),
            "materials": item.get("준비물"),
            "safety_notes": item.get("safety_notes(안전)"),
            "external_path": item.get("외부시작경로"),
            "rag_description": item.get("RAG설명(임베딩본문)"),
            "rag_keywords": item.get("RAG검색키워드"),
            "is_synthetic": item.get("is_synthetic", False),
            "cost_verification": item.get("비용검증상태"),
            "safety_verification": item.get("안전검증상태"),
            "fallback_set": item.get("fallback_set", False)
        }
        db_data.append(mapped_item)
        
    try:
        # hobby_profile 테이블에 upsert 수행
        # primary key인 hobby_id를 기준으로 매칭되어 중복 덮어쓰기됩니다.
        response = supabase_client.table("hobby_profile").upsert(db_data).execute()
        print(f"Supabase RDB 적재 완료! 총 {len(db_data)}개의 아이템이 업서트되었습니다.")
    except Exception as e:
        print(f"❌ Supabase 적재 중 오류 발생: {e}")
        print("주의: Supabase에 테이블(hobby_profile)이 생성되지 않았을 수 있습니다. schema.sql을 먼저 실행했는지 확인하세요.")

def main():
    # sys.argv에 '--dummy'가 포함되어 있거나 환경변수 SEED_DUMMY=true 이면 dummy 모드로 구동
    dummy_mode = "--dummy" in sys.argv or os.getenv("SEED_DUMMY", "").lower() == "true"
    
    openai_client = None
    if not dummy_mode:
        if not OPENAI_API_KEY:
            print("❌ 에러: OPENAI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 작성해 주세요.")
            print("대신 '--dummy' 플래그를 붙여 실행하면 OpenAI API 없이 ChromaDB에 임시 시딩할 수 있습니다.")
            print("실행 예시: python backend/seed_data.py --dummy")
            return
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        
    try:
        profiles = load_and_sanitize_data(DATA_FILE_PATH)
        
        # 1. ChromaDB 적재 (로컬 파일 기반이므로 항상 먼저 진행 가능)
        seed_chromadb(profiles, openai_client, dummy=dummy_mode)
        
        # 2. Supabase RDB 적재 (URL/Key 설정이 되어 있을 때만 실행)
        seed_supabase(profiles)
        
        print("🎉 모든 시딩 과정이 완료되었습니다!")
        
    except Exception as e:
        print(f"❌ 실행 중 에러가 발생했습니다: {e}")

if __name__ == "__main__":
    main()
