# 노동법 RAG 챗봇 — 기술 문서

> 대상 독자: 백엔드/프론트엔드 개발자, ML 엔지니어, DevOps 엔지니어

---

## 1. 아키텍처 개요

### 1.1 전체 시스템 구성

```
┌────────────────────────────────────────────────────────────────┐
│  Streamlit UI (app_chatbot.py)                                  │
│  @st.fragment: 채팅 영역 부분 리런                              │
│  @st.cache_resource: 그래프·벡터스토어 싱글턴                   │
└──────────────┬─────────────────────────────────────────────────┘
               │ graph.invoke() / direct pipeline calls
┌──────────────▼─────────────────────────────────────────────────┐
│  LangGraph State Machine (rag/graph.py)                         │
│  State: messages, phase, situation, issues, checklist, qa_list │
│  Node: chatbot_node → route_after_chatbot → END                 │
└──────────────┬─────────────────────────────────────────────────┘
               │
┌──────────────▼─────────────────────────────────────────────────┐
│  RAG Pipeline (rag/pipeline.py)                                 │
│  step1_and_step2_parallel → step2_checklist → step3_conclusion │
└──────┬──────────────────────┬──────────────────────────────────┘
       │                      │
┌──────▼──────┐    ┌──────────▼────────────┐
│  ChromaDB   │    │  OpenAI API            │
│  (store.py) │    │  LLM: gpt-5-nano       │
│  임베딩 검색 │    │  Embedding: text-      │
│  vector_    │    │  embedding-3-large     │
│  store/     │    │  (공식 엔드포인트 강제) │
└─────────────┘    └───────────────────────┘
       ▲
┌──────┴──────────────────────────────────────────────────────────┐
│  법령 JSON 데이터 (api_data/laws/, terms/, bylaws/ ...)          │
│  국가법령정보 API → scripts/sync_all.py (주 1회 자동 동기화)     │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 핵심 파일 구조

```
webapp/
├── app_chatbot.py          # Streamlit 서비스용 챗봇 UI (1,340 라인)
├── app.py                  # 개발/기획자용 4단계 상세 UI
├── config.py               # 환경변수 로딩, 전역 상수 정의
├── main.py                 # CLI 진입점
├── requirements.txt        # Python 의존성
├── rag/
│   ├── graph.py            # LangGraph 상태 머신 (942 라인)
│   ├── pipeline.py         # RAG 3단계 파이프라인 (1,637 라인)
│   ├── store.py            # ChromaDB 벡터스토어 래퍼 (286 라인)
│   ├── llm.py              # OpenAI LLM 호출 래퍼 (272 라인)
│   ├── prompts.py          # 시스템/유저 프롬프트 팩토리 (332 라인)
│   ├── law_json.py         # 법령 JSON 데이터 접근 (395 라인)
│   ├── load_laws.py        # 법령 문서 로딩 및 청킹
│   ├── labor_keywords.py   # 노동법 키워드 사전
│   ├── question_classifier.py  # 질문 유형 분류 (정보/계산/상황)
│   ├── capabilities.py     # 연관 질문 가능 유형 정의
│   ├── law_classification.py   # 이슈별 관련 법률 자동 분류
│   ├── api_cache.py        # API 응답 캐싱
│   ├── api_data_loader.py  # api_data/ JSON 로더
│   └── ...
├── vector_store/           # ChromaDB 영구 저장소
├── api_data/               # 법령 원본 JSON (sync_all.py로 생성)
├── scripts/                # 동기화/테스트 스크립트
├── docs/                   # 기술 문서
└── .streamlit/config.toml  # Streamlit 설정
```

---

## 2. 핵심 모듈 상세

### 2.1 RAG 파이프라인 (`rag/pipeline.py`)

#### 2.1.1 Step1 — 이슈 분류

**함수**: `step1_and_step2_parallel(situation, collection, top_k=22) → dict`

**경로 A (키워드 매칭, 빠른 경로)**:
```python
# labor_keywords.py의 키워드 사전으로 즉시 이슈 확정
candidate_issues = get_categories_for_issue(situation)
# 예: "퇴직금을 못받았어" → ["퇴직금"]
```

**경로 B (LLM 분류, 느린 경로)**:
```python
# 키워드 매칭 실패 시 LLM으로 이슈 분류
issues, articles_by_issue, source = _classify_with_llm(situation, collection, top_k)
```

**반환 구조**:
```python
{
    "issues": ["퇴직금"],
    "articles_by_issue": {"퇴직금": [{"text": ..., "article": ..., "source": ...}]},
    "selected_issue": "퇴직금",
    "checklist": [{"question": "...", "type": "binary"}],
    "rag_results": [{"text": ..., "article": ..., "source": ...}],
    "source": "keyword",  # "keyword" | "llm"
}
```

#### 2.1.2 Step2 — 체크리스트 생성

**함수**: `step2_checklist(issue, filter_text, collection, narrow_answers, qa_list, remaining_articles) → dict`

```python
# 1. 조문 컨텍스트 구성
context = _rag_context(remaining_articles, max_length=CHECKLIST_CONTEXT_MAX_LENGTH)

# 2. LLM 체크리스트 생성
checklist = chat_json(
    system_checklist(issue),
    user_checklist(issue, situation, context),
    max_tokens=CHECKLIST_MAX_TOKENS,
    reasoning_effort="low"
)

# 3. 지속 여부 판단 (2차 라운드 필요성)
should_continue = chat_json(
    system_checklist_continuation(issue),
    user_checklist_continuation(issue, all_qa),
    reasoning_effort="low"
)
```

**반환 구조**:
```python
{
    "checklist": [{"question": "...", "options": ["네", "아니요", "모르겠음"]}],
    "rag_results": [{"text": ..., "article": ..., "source": ...}],
    "should_continue": False,
    "continuation_reason": "",
}
```

#### 2.1.3 Step3 — 결론 생성 (스트리밍)

**함수**: `step3_conclusion_stream(issue, qa_list, collection, narrow_answers) → Generator[str]`

**4단계 컨텍스트 수집 후 스트리밍**:

```
1차: 법률 조문 검색 (preferred_sources 우선, 전체 fallback)
     └→ classify_laws_for_issue()로 이슈 관련 법률 자동 감지
2차: 관련 조문 확장 (related_articles API)
3차: 시행령·시행규칙 검색 (ThreadPoolExecutor 병렬)
4차: 판례·고용노동부 해석 검색 (ThreadPoolExecutor 병렬)
     └→ 컨텍스트 조합 완료
     └→ chat_stream() 시작 → yield chunk
```

**`narrow_answers` 타입 안전 처리**:
```python
def _to_str_s(x):
    if isinstance(x, str): return x
    if isinstance(x, dict): return x.get('text', x.get('article', x.get('content', '')))
    return str(x)
# str/dict 리스트 모두 처리 가능 (TypeError 방지)
```

---

### 2.2 벡터스토어 (`rag/store.py`)

#### 임베딩 클라이언트 설정

```python
# 임베딩은 항상 공식 OpenAI 엔드포인트 강제 사용
OPENAI_OFFICIAL_BASE_URL = "https://api.openai.com/v1"

def _get_embedding_client() -> OpenAI:
    # OPENAI_BASE_URL 환경변수 무시
    # (Genspark 프록시 등 LLM 전용 프록시는 임베딩 API 미지원 → 404)
    return OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_OFFICIAL_BASE_URL)
```

#### LRU 캐시 (임베딩 재사용)

```python
@lru_cache(maxsize=500)
def get_embedding(text: str, model: str = EMBEDDING_MODEL) -> tuple:
    # 동일 쿼리 재계산 없이 재사용
    return tuple(client.embeddings.create(input=[text], model=model).data[0].embedding)
```

#### 검색 함수

```python
def search(
    collection,
    query: str,
    top_k: int = 10,
    filter_sources: Optional[List[str]] = None,
    exclude_sections: Optional[List[str]] = None,
    exclude_chapters: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    # ChromaDB where 절로 법률 소스/섹션/장 필터링
    # 임베딩 cosine similarity 검색
```

#### ChromaDB 컬렉션

- **이름**: `labor_law_articles`
- **임베딩 모델**: `text-embedding-3-large` (3072차원)
- **저장 위치**: `vector_store/` (ChromaDB PersistentClient)
- **메타데이터 필드**: `source`, `article`, `section`, `chapter`

---

### 2.3 LangGraph 상태 머신 (`rag/graph.py`)

#### 상태 스키마

```python
class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 대화 히스토리
    situation: str           # 사용자 상황 설명
    issues: list[str]        # 분류된 이슈 목록
    selected_issue: str      # 선택된 주 이슈
    qa_list: list[dict]      # 체크리스트 Q&A 누적
    articles_by_issue: dict  # 이슈별 관련 조문
    checklist: list          # 현재 체크리스트
    checklist_index: int     # 현재 체크리스트 인덱스
    phase: str               # "input" | "checklist" | "conclusion"
    pending_question: str    # 대기 중인 질문
    checklist_rag_results: list  # step2 조문 (다음 라운드용)
```

#### 그래프 노드

```
START → chatbot_node → route_after_chatbot → END
                              │
                     ┌────────┴────────┐
              [계속 진행]          [종료]
         다시 chatbot_node로          END
```

#### 질문 유형 분류 (graph.py)

그래프는 사용자 입력 타입을 자동 감지하여 분기:

| 질문 유형 | 처리 방식 | 예시 |
|-----------|-----------|------|
| `information` | RAG 검색 + 정보 답변 | "퇴직금 지급기한이 언제야?" |
| `calculation` | 계산 로직 + RAG 검변 | "퇴직금 얼마야?" |
| `situation` | 풀 파이프라인 (step1→step3) | "퇴직금을 못받았어" |
| `exception` | 예외 처리 | 노동법 범위 외 질문 |

---

### 2.4 Streamlit 앱 (`app_chatbot.py`)

#### @st.fragment 적용

```python
@st.fragment
def _render_chat_ui():
    """채팅 영역 전용 fragment. 여기서의 st.rerun()은 채팅 영역만 재실행."""
    ...
    # 체크리스트 버튼, 관련질문 버튼, 폴링 루프 → st.rerun() (fragment 기본)
    # 조항 상세 이동 → st.rerun(scope="app")
```

#### rerun 범위 정책

| 이벤트 | scope | 이유 |
|--------|-------|------|
| 체크리스트 버튼 (네/아니요/모르겠음) | fragment | 채팅 영역만 갱신 |
| "다음 →" 버튼 | fragment | 체크리스트 제출, 채팅 영역 내 처리 |
| 관련질문 버튼 클릭 | fragment | 메시지 추가 후 채팅 영역 재실행 |
| 처리 중 폴링 (`time.sleep(1)`) | fragment | 백그라운드 결과 폴링 |
| 결과 도착 후 반영 | app | 전체 앱 갱신으로 채팅에 표시 |
| 조항 상세 보기 클릭 | app | 사이드바 + 메인 레이아웃 변경 |
| 사이드바 조문 클릭 | app | 전체 레이아웃 전환 |
| 예시 질문 버튼 | fragment | 채팅 영역 내 메시지 추가 |
| 새 대화 시작 | auto (callback) | Streamlit 콜백 자동 rerun |

#### 백그라운드 처리 아키텍처

```python
# 1. 사용자 메시지 → 처리 placeholder 추가 → 백그라운드 스레드 시작
req_id = str(uuid.uuid4())[:12]
st.session_state.messages.append(AIMessage(content=CHECKLIST_PROCESSING_MSG))
st.session_state._processing_request_id = req_id
t = threading.Thread(target=_run_invoke, args=(req_id, last_human, config), daemon=True)
t.start()
st.rerun()  # fragment 재실행 → 폴링 루프 진입

# 2. 백그라운드 스레드: graph.invoke() 실행 → 결과를 메모리+파일에 저장
def _run_invoke(req_id, msg, config):
    r = graph.invoke({"messages": [msg]}, config=config)
    _pending_result[req_id] = ("ok", r)        # 메모리 (같은 프로세스용)
    _pending_path(req_id).write_text(json.dumps(...))  # 파일 (멀티워커용)

# 3. 폴링 루프: 결과 확인 후 st.rerun(scope="app")
for _ in range(15):  # 최대 4.5초 대기
    if result_file.exists():
        res = load_and_deserialize(result_file)
        apply_to_session_state(res)
        st.rerun(scope="app")  # 전체 앱 갱신
    time.sleep(0.3)

# 4. main() 초기: 사이드바 법률탐색 중 결과 자동 픽업
# (사이드바 클릭 → scope="app" rerun → main() 재실행 → 결과 감지)
if _still_pending:
    _bg_res = _check_memory_or_file(req_id)
    if _bg_res:
        apply_to_session_state(_bg_res)
        st.session_state._result_just_arrived = True
```

#### 세션 상태 키 목록

| 키 | 타입 | 설명 |
|----|------|------|
| `messages` | `list[BaseMessage]` | 전체 대화 히스토리 |
| `thread_id` | `str` | LangGraph 체크포인트 ID |
| `cb_checklist` | `list` | 현재 체크리스트 항목 |
| `cb_checklist_answers` | `dict[int, str]` | 체크리스트 답변 (idx → 답변) |
| `cb_checklist_submitted` | `bool` | 체크리스트 제출 완료 여부 |
| `cb_issue` | `str` | 현재 이슈 |
| `cb_situation` | `str` | 사용자 상황 원문 |
| `cb_articles_by_issue` | `dict` | 이슈별 조문 목록 |
| `cb_round` | `int` | 현재 체크리스트 라운드 (1~3) |
| `cb_all_qa` | `list` | 전체 Q&A 누적 |
| `cb_checklist_rag_results` | `list` | 체크리스트용 RAG 결과 |
| `related_questions` | `list[str]` | 연관 질문 목록 |
| `pending_buttons` | `list[str]` | 타겟/그룹 선택 버튼 레이블 |
| `_processing_request_id` | `str \| None` | 백그라운드 요청 ID |
| `processing_step` | `int` | 스피너 단계 (0~3) |
| `browse_view` | `str \| None` | 사이드바 조문 보기 상태 |
| `sidebar_open` | `bool` | 사이드바 열림 여부 |
| `_result_just_arrived` | `bool` | 결과 방금 도착 플래그 (뱃지용) |

---

### 2.5 LLM 클라이언트 (`rag/llm.py`)

#### 클라이언트 설정

```python
def _get_chat_client() -> OpenAI:
    kwargs = {"api_key": OPENAI_API_KEY}
    if OPENAI_BASE_URL:  # 프록시 설정 시 LLM 호출에만 적용
        kwargs["base_url"] = OPENAI_BASE_URL
    return OpenAI(**kwargs)
```

#### 주요 함수

| 함수 | 설명 | 반환 |
|------|------|------|
| `chat(system, user, model, max_tokens, reasoning_effort)` | 단일 LLM 호출 | `str` |
| `chat_stream(system, user, model, ...)` | 스트리밍 LLM 호출 | `Generator[str]` |
| `chat_json(system, user, max_tokens, reasoning_effort)` | JSON 응답 파싱 | `Any` (list/dict) |
| `chat_json_fast(system, user, max_tokens)` | reasoning_effort=low로 빠른 JSON 파싱 | `Any` |
| `extract_json(text)` | 텍스트에서 JSON 블록 추출 | `Any \| None` |

#### gpt-5-nano 특성

```python
is_reasoning = "gpt-5" in model or "nano" in model.lower()
if is_reasoning:
    kwargs["temperature"] = 1  # reasoning 모델은 temperature=1 고정
    kwargs["reasoning_effort"] = "low"  # 속도 최적화
    # max_completion_tokens 사용 (max_tokens 대신)
    # effort=low → 최소 2000 토큰 필요
```

---

### 2.6 프롬프트 팩토리 (`rag/prompts.py`)

```python
# 이슈 분류 프롬프트
system_issue_classification() → str
user_issue_classification(situation, rag_context) → str

# 체크리스트 프롬프트
system_checklist(issue) → str
user_checklist(issue, situation, rag_context) → str
system_checklist_continuation(issue) → str
user_checklist_continuation(issue, qa_list) → str

# 결론 프롬프트
system_conclusion(issue) → str
user_conclusion(issue, qa_text, law_context, decree_context, precedent_context) → str

# 연관 질문 프롬프트
system_related_questions(capabilities) → str
user_related_questions(conclusion, issue, capabilities) → str

# 오프토픽 감지 프롬프트
system_off_topic_detection() → str
user_off_topic_detection(text) → str
```

---

## 3. 데이터 파이프라인

### 3.1 법령 데이터 동기화

```
scripts/sync_all.py
├── sync_laws.py      → api_data/laws/{법령명}/    (법령 본문 JSON)
├── sync_terms.py     → api_data/terms/            (용어 정의)
├── sync_bylaws.py    → api_data/bylaws/            (시행령·시행규칙)
├── sync_related.py   → api_data/related/           (연관 법령)
└── sync_precedents.py → api_data/precedents/       (판례)
```

### 3.2 벡터스토어 구축

```python
def build_vector_store(force_rebuild=False):
    # 1. ChromaDB 컬렉션 확인 (이미 있으면 기존 것 반환)
    # 2. api_data/laws/의 JSON → load_laws_auto()로 문서 청킹
    # 3. get_embeddings_batch()로 배치 임베딩 (1회 API 호출로 N개 처리)
    # 4. ChromaDB에 upsert
    return collection, was_built
```

### 3.3 문서 청킹 전략 (`rag/load_laws.py`)

- 단위: 법령 조문(Article) 1개 = 1 ChromaDB 문서
- 메타데이터: `source` (법령명), `article` (조번호), `section` (편/장), `chapter` (장)
- 조문이 너무 길면 항 단위로 분할

---

## 4. 성능 최적화

### 4.1 인메모리 캐싱

| 캐시 | 위치 | 크기/TTL |
|------|------|-----------|
| 벡터스토어 컬렉션 | `@st.cache_resource` | 프로세스 수명 |
| LangGraph 그래프 | `@st.cache_resource` | 프로세스 수명 |
| 임베딩 | `@lru_cache(maxsize=500)` | 프로세스 수명 |
| 법령 목록 | `@st.cache_data(ttl=3600)` | 1시간 |
| 법령 장/조문 | `@st.cache_data(ttl=3600)` | 1시간 |
| 업데이트 날짜 | `@st.cache_data(ttl=60)` | 1분 |

### 4.2 병렬 실행

```python
# step3_conclusion_stream: 시행령·판례 검색 병렬
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
    fut_decree = ex.submit(_fetch_decree)  # 시행령·시행규칙
    fut_prec   = ex.submit(_fetch_prec)    # 판례·법령해석
    decree_rule_results = fut_decree.result()
    precedents_context  = fut_prec.result()

# step1_and_step2_parallel: 조문 수집과 체크리스트 생성 병렬
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
    step1_future = ex.submit(_do_step1)  # 이슈별 조문 수집
    articles_by_issue = step1_future.result()
# 즉시 step2 시작 (step1 완료 후)
```

### 4.3 스트리밍

```python
# rag/llm.py: chat_stream
def chat_stream(system, user, model, ...) -> Generator[str]:
    stream = client.chat.completions.create(..., stream=True)
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta

# app_chatbot.py: Streamlit write_stream
with st.chat_message("assistant"):
    conclusion_text = st.write_stream(
        step3_conclusion_stream(cb_issue, all_qa, col, narrow_answers)
    )
```

---

## 5. 오류 처리 상세

### 5.1 임베딩 API 오류 방지

```python
# store.py: 임베딩 클라이언트는 항상 공식 엔드포인트
# 환경변수 OPENAI_BASE_URL이 설정되어도 임베딩에는 무시
OPENAI_OFFICIAL_BASE_URL = "https://api.openai.com/v1"
_embedding_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_OFFICIAL_BASE_URL)
```

### 5.2 narrow_answers 타입 안전성

```python
# pipeline.py: step3_conclusion, step3_conclusion_stream
# narrow_answers가 str 리스트 또는 dict 리스트 모두 처리
def _to_str(x):
    if isinstance(x, str): return x
    if isinstance(x, dict): return x.get('text', x.get('article', x.get('content', '')))
    return str(x)
narrow_strs = [s for s in (_to_str(x) for x in narrow_answers) if s]
```

### 5.3 LLM 응답 빈 값 처리

```python
# llm.py: content가 None인 경우 delta에서 재시도
if content is None:
    if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
        content = choice.delta.content
    return ""
```

### 5.4 백그라운드 스레드 오류 격리

```python
def _run_invoke(req_id, msg, config):
    try:
        r = graph.invoke(...)
        _pending_result[req_id] = ("ok", r)
    except Exception as e:
        _pending_result[req_id] = ("error", str(e))
        # 파일에도 기록 (멀티워커 환경)
        _pending_path(req_id).write_text(json.dumps({"status":"error","error":str(e)}))
```

---

## 6. 환경별 설정

### 6.1 개발 환경 (로컬)

```bash
# .env 파일
OPENAI_API_KEY=sk-proj-...
LAW_API_OC=your_api_oc_token
LAW_CHAT_MODEL=gpt-5-nano
LAW_EMBEDDING_MODEL=text-embedding-3-large

# 실행
streamlit run app_chatbot.py --server.port 8501
```

### 6.2 Streamlit Cloud

```toml
# st.secrets (Streamlit Cloud 대시보드에서 설정)
OPENAI_API_KEY = "sk-proj-..."
LAW_API_OC = "your_token"
# OPENAI_BASE_URL 절대 설정하지 않을 것 (임베딩 404 오류 발생)
```

`config.py`의 `_inject_streamlit_secrets()`가 자동으로 `st.secrets` → `os.environ` 주입.

### 6.3 Genspark/프록시 환경 (주의)

```python
# 환경변수 OPENAI_BASE_URL이 프록시 URL인 경우:
# - LLM 호출 (llm.py): 프록시 사용 → gpt-5-nano 정상 동작
# - 임베딩 (store.py): 공식 엔드포인트 강제 → text-embedding-3-large 정상 동작
# 즉, OPENAI_BASE_URL이 있어도 임베딩은 프록시 우회하여 공식 API 사용
```

### 6.4 환경변수 우선순위

```
1. 시스템 환경변수 (os.environ)
2. .env 파일 (python-dotenv, load_dotenv())
3. st.secrets (Streamlit Cloud, _inject_streamlit_secrets())
```

---

## 7. 테스트

### 7.1 파이프라인 단위 테스트

```bash
# 전체 파이프라인 테스트 (약 30~45초 소요)
cd /home/user/webapp
OPENAI_API_KEY=sk-... python3 -c "
from rag.store import build_vector_store
from rag.pipeline import step1_and_step2_parallel, step3_conclusion_stream
col, _ = build_vector_store()
r = step1_and_step2_parallel('퇴직금을 못받았어', col)
qa = [{'question': item.get('question',''), 'answer': '네'} for item in r['checklist']]
for chunk in step3_conclusion_stream(r['selected_issue'], qa, col, r['rag_results']):
    print(chunk, end='', flush=True)
"
```

### 7.2 LLM API 연결 테스트

```bash
python3 -c "
import openai, os
os.environ.pop('OPENAI_BASE_URL', None)
client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
r = client.chat.completions.create(model='gpt-4.1-nano', messages=[{'role':'user','content':'test'}], max_tokens=10)
print('LLM OK:', r.choices[0].message.content)
"
```

### 7.3 임베딩 테스트

```bash
python3 -c "
from rag.store import get_embedding
v = get_embedding('퇴직금')
print('임베딩 OK, 차원:', len(v))
"
```

### 7.4 시나리오 테스트 (`scripts/test_scenarios.py`)

```bash
python scripts/test_scenarios.py
# 주요 시나리오 자동 검증:
# - 퇴직금 미지급
# - 해고 통보
# - 연장근무 수당 미지급
# - 육아휴직 거부
# - 최저임금 위반
```

---

## 8. 배포 체크리스트

### 8.1 최초 배포

- [ ] `OPENAI_API_KEY` 환경변수/secrets 설정 확인
- [ ] `LAW_API_OC` 설정 (법령 동기화용)
- [ ] `OPENAI_BASE_URL` **미설정** 확인 (임베딩 오류 방지)
- [ ] `python scripts/sync_all.py` 법령 데이터 동기화 완료
- [ ] `python main.py --rebuild` 벡터스토어 구축 완료
- [ ] `streamlit run app_chatbot.py` 앱 정상 실행 확인
- [ ] "퇴직금을 못받았어" 입력 후 체크리스트 생성 확인 (Step1+2: ~12초 내)
- [ ] 체크리스트 완료 후 결론 생성 확인 (첫 토큰: ~10초 내)
- [ ] 연관 질문 버튼 정상 동작 확인

### 8.2 업데이트

- [ ] `git pull` 최신 코드 반영
- [ ] `python scripts/sync_all.py` (법령 변경 시)
- [ ] `python main.py --rebuild` (법령 변경 시)
- [ ] 앱 재시작

---

## 9. 알려진 제약사항

| 항목 | 내용 |
|------|------|
| 멀티워커 | `.streamlit_pending/` 임시 파일로 프로세스 간 결과 공유. 단일 워커 권장 |
| Cold Start | Streamlit Cloud cold start 시 벡터스토어 재구축 1~2분 소요 |
| 토큰 한계 | gpt-5-nano reasoning_effort=low 시 약 4,000 max_completion_tokens |
| 체크리스트 최대 | 한 라운드당 최대 7개 질문, 최대 3라운드 |
| 결론 길이 | 평균 1,500~3,000자 |
| 동시 처리 | Streamlit 단일 스레드 UI + 백그라운드 스레드 1개 |
