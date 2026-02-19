# 노동법 RAG 챗봇 설정
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL = os.getenv("LAW_CHAT_MODEL", "gpt-5-nano")
EMBEDDING_MODEL = os.getenv("LAW_EMBEDDING_MODEL", "text-embedding-3-large")

# 법령 데이터 (API 전용: api_data/ 사용, 로컬 laws/ 미사용)
VECTOR_DIR = Path(__file__).resolve().parent / "vector_store"

# API 기반 데이터. 저장·캐시 전략: docs/API_STORAGE_STRATEGY.md
# resolve()로 절대 경로 고정 → Streamlit 등 cwd와 무관하게 동일 경로 사용
_BASE = Path(__file__).resolve().parent
API_DATA_DIR = (_BASE / "api_data").resolve()
LAWS_DATA_DIR = (API_DATA_DIR / "laws").resolve()
TERMS_DATA_DIR = (API_DATA_DIR / "terms").resolve()
PRECEDENTS_DATA_DIR = (API_DATA_DIR / "precedents").resolve()
BYLAWS_DATA_DIR = (API_DATA_DIR / "bylaws").resolve()
RELATED_DATA_DIR = (API_DATA_DIR / "related").resolve()
CACHE_DIR = (API_DATA_DIR / "cache").resolve()

# 문서 소스(= 법령명). 검색 단계별로 필터링에 사용.
# 개별적 근로관계법
SOURCE_LAW = "근로기준법(법률)"
SOURCE_DECREE = "근로기준법(시행령)"
SOURCE_RULE = "근로기준법(시행규칙)"
SOURCE_MIN_WAGE_LAW = "최저임금법(법률)"
SOURCE_RETIREMENT_LAW = "근로자퇴직급여 보장법(법률)"
SOURCE_GENDER_EQUALITY_LAW = "남녀고용평등과 일·가정 양립 지원에 관한 법률(법률)"
SOURCE_PART_TIME_LAW = "기간제 및 단시간근로자 보호 등에 관한 법률(법률)"

# 집단적 노사관계법
SOURCE_UNION_LAW = "노동조합 및 노동관계조정법(법률)"
SOURCE_PARTICIPATION_LAW = "근로자참여 및 협력증진에 관한 법률(법률)"

# 노동시장 및 협력적 법률
SOURCE_SAFETY_LAW = "산업안전보건법(법률)"
SOURCE_EMPLOYMENT_INSURANCE_LAW = "고용보험법(법률)"
SOURCE_JOB_STABILITY_LAW = "직업안정법(법률)"
SOURCE_INDUSTRIAL_ACCIDENT_LAW = "산업재해보상보험법(법률)"

# 모든 노동법 소스 목록 (검색 시 사용)
ALL_LABOR_LAW_SOURCES = [
    SOURCE_LAW,
    SOURCE_MIN_WAGE_LAW,
    SOURCE_RETIREMENT_LAW,
    SOURCE_GENDER_EQUALITY_LAW,
    SOURCE_PART_TIME_LAW,
    SOURCE_UNION_LAW,
    SOURCE_PARTICIPATION_LAW,
    SOURCE_SAFETY_LAW,
    SOURCE_EMPLOYMENT_INSURANCE_LAW,
    SOURCE_JOB_STABILITY_LAW,
    SOURCE_INDUSTRIAL_ACCIDENT_LAW,
]

# 개별적 근로관계법 소스만 (기본 검색)
INDIVIDUAL_LABOR_LAW_SOURCES = [
    SOURCE_LAW,
    SOURCE_MIN_WAGE_LAW,
    SOURCE_RETIREMENT_LAW,
    SOURCE_GENDER_EQUALITY_LAW,
    SOURCE_PART_TIME_LAW,
]

# 집단적 노사관계법 소스
COLLECTIVE_LABOR_LAW_SOURCES = [
    SOURCE_UNION_LAW,
    SOURCE_PARTICIPATION_LAW,
]

# 노동시장 및 협력적 법률 소스
LABOR_MARKET_LAW_SOURCES = [
    SOURCE_SAFETY_LAW,
    SOURCE_EMPLOYMENT_INSURANCE_LAW,
    SOURCE_JOB_STABILITY_LAW,
    SOURCE_INDUSTRIAL_ACCIDENT_LAW,
]

# RAG
RAG_TOP_K = 10  # 검색 속도 향상을 위해 15 → 10으로 감소
RAG_SCORE_THRESHOLD = 0.0  # 필요시 상향

# 이슈별 조문 검색 단계별 top_k (유연한 조정용)
RAG_MAIN_TOP_K = 18   # 메인 검색(총칙 제외)
RAG_AUX_TOP_K = 10    # 보조 검색(총칙 포함)
RAG_DEF_TOP_K = 10    # 정의 전용 검색
RAG_FILTER_TOP_K = 20  # 관련도 필터 후 유지 개수 (체크리스트에 더 많은 조문 반영)
CHECKLIST_MAX_ITEMS = 7  # 체크리스트 한 차수당 최대 질문 개수 (과다 방지)
CHECKLIST_CONTEXT_MAX_LENGTH = 3600  # 체크리스트용 RAG 컨텍스트 글자 수 (축소 시 응답 속도 향상, 품질 유지)
CHECKLIST_MAX_TOKENS = 4096  # 체크리스트 LLM 응답 상한 (낮추면 reasoning 모델도 빨리 종료 → 속도 향상, 비어있으면 파이프라인에서 재시도)
CHECKLIST_MAX_ARTICLES = 10  # 체크리스트 생성 시 참조할 최대 조문 수 (과다 시 컨텍스트만 커져 지연)
STEP1_ISSUE_SEARCH_TOP_N = 3  # step1에서 이슈별 검색으로 조문 수집하는 최대 이슈 수 (나머지는 공통 베이스만)

# 총칙 판별용 장 번호 (JSON chapter.number와 비교)
GENERAL_CHAPTER_NUMBERS = frozenset({"제1장"})

# 규칙: RAG에 없는 내용은 "해당 내용은 제공된 법령 데이터에 없습니다." 로만 답변

# 국가법령정보 공동활용 API (봇 차단 방지를 위해 모든 요청에 브라우저 헤더 사용)
LAW_API_OC = os.getenv("LAW_API_OC", "")
LAW_API_TIMEOUT = int(os.getenv("LAW_API_TIMEOUT", "30"))
LAW_API_DELAY_SEC = float(os.getenv("LAW_API_DELAY_SEC", "2.0"))  # 요청 간 기본 딜레이(초) - 봇 차단 방지를 위해 2초로 증가

# 법령 시행일 기준 연도 (설정 시 해당 연도 시행법령 사용. 미설정이면 현행법령(공포일) 기준)
# 예: LAW_EFFECTIVE_YEAR=2024 → eflaw API + efYd=20240101~20241231
_def = os.getenv("LAW_EFFECTIVE_YEAR", "").strip()
LAW_EFFECTIVE_YEAR = int(_def) if _def.isdigit() else None
