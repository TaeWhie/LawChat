# LawChat 백엔드 API 사용 가이드

본 문서는 Render에 배포된 LawChat API의 주요 엔드포인트와 사용 방법을 안내합니다.

**서버 Base URL:** Render에 배포한 뒤 **Render 대시보드 → 해당 Web Service → 상단에 표시되는 URL**을 사용합니다. 예: `https://law-chat-api.onrender.com/`

모든 POST API 요청은 JSON 요청 바디(`application/json`)를 사용합니다.

---

## 🔑 전역 공통 파라미터 (동적 API 키·모델 주입)

**모든 POST 요청 바디**에 다음을 선택적으로 포함할 수 있습니다. 넘기지 않으면 서버 환경변수(OPENAI_API_KEY, LAW_API_OC 등)가 사용됩니다.

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `openai_api_key` | string | OpenAI(또는 호환) API 키 |
| `openai_base_url` | string | OpenAI Base URL (Azure·프록시 등, Render 단일 배포 시 보통 생략) |
| `law_api_key` | string | 국가법령정보 API OC 키 (서류·법령 검색 시) |
| `model` | string | 채팅 모델 오버라이드 (예: `gpt-4o`, `gpt-4o-mini`. 미설정 시 서버 LAW_CHAT_MODEL 사용) |

---

## 0. 루트(/) 접속

브라우저에서 **Base URL만** 열면(예: `https://law-chat-api.onrender.com/`) API 안내 JSON이 반환됩니다.

- **URL:** `GET /`
- **응답 예시:**
  ```json
  {
    "service": "LawChat Backend API",
    "docs": "/docs",
    "health": "/api/v1/health",
    "message": "API 사용법은 GET /docs 에서 확인하세요."
  }
  ```
  - `docs`: Swagger UI 경로 (`/docs` 에서 API 명세·테스트)
  - `health`: 서버 상태 확인 경로 (`/api/v1/health`)

---

## 1. 서버 헬스체크 및 버전 확인

- **URL:** `GET /api/v1/health`
- **응답 예시:**
  ```json
  {
    "status": "ok",
    "version": "1.2.0",
    "context_supported": true
  }
  ```
  `version`은 환경변수 `LAW_API_VERSION`으로 설정 가능 (기본 `1.2.0`).

---

## 2. ★ 권장: 1회 상담 (invoke) — 챗봇과 동일 동작

**한 번의 호출로** 챗봇(app_chatbot)과 동일한 RAG 플로우(라우팅·이슈분류·체크리스트·결론·지식/계산/서류 분기)를 실행합니다. 프론트엔드는 이 엔드포인트만 사용하는 것을 권장합니다.

- **URL:** `POST /api/v1/chat/invoke`
- **Request Body:**
  ```json
  {
    "message": "월급을 두 달째 못 받았어요",
    "thread_id": "user-123",
    "openai_api_key": "sk-proj-...",
    "model": "gpt-4o-mini"
  }
  ```
  - `message` (필수): 사용자 입력 메시지
  - `thread_id` (선택): 대화 스레드 ID. 체크리스트·다음 턴 시 동일 ID 사용 (기본 `"default"`)
  - 위 공통 파라미터(`openai_api_key`, `openai_base_url`, `law_api_key`, `model`) 선택 사용

- **Response:**
  ```json
  {
    "status": "ok",
    "messages": [{ "t": "HumanMessage", "c": "..." }, { "t": "AIMessage", "c": "..." }],
    "phase": "input" | "checklist" | "conclusion",
    "checklist": [...],
    "selected_issue": "...",
    "situation": "...",
    "articles_by_issue": { ... },
    "checklist_rag_results": [ ... ]
  }
  ```
  체크리스트 후 다음 사용자 답변을 보낼 때도 같은 `thread_id`로 `message`만 바꿔서 다시 `POST /api/v1/chat/invoke` 호출하면 됩니다.

---

## 3. 질문 라우팅 (의도 파악)

사용자의 입력이 어떤 유형의 질문인지(지식, 계산, 문서, 일반 등) 판별합니다.

- **URL:** `POST /api/v1/chat/route`
- **Request Body:** `text` (필수) + 공통 파라미터 선택
- **Response:** `{ "question_type": "calculation_qa" | "knowledge_qa" | "exception_qa" | "document_qa" | "general" 등 }`

---

## 4. 노동법 RAG 파이프라인 (단계별 — 디버깅·커스텀 UI용)

LawChat의 핵심인 사안 분류 -> 체크리스트 -> 최종 결론 3단계 프로세스입니다.

### 단계 4-1: 사안 분류 (Issue Classification)
사용자의 상황을 읽고 연관된 노동법 핵심 이슈들을 추출합니다.

- **URL:** `POST /api/v1/chat/classify`
- **Request Body:**
  ```json
  {
    "situation": "편의점에서 1년 넘게 일했는데 퇴직금을 안 줍니다.",
    "top_k": 22,
    "openai_api_key": "sk-proj-..."
  }
  ```
- **Response:**
  ```json
  {
    "status": "success",
    "issues": ["퇴직금", "임금"],
    "articles_by_issue": {
      "퇴직금": [{...조문 데이터...}]
    }
  }
  ```

### 단계 4-2: 체크리스트 및 추가 질의 (Checklist)
추출된 이슈를 바탕으로 정확한 사실관계를 판단하기 위한 질문과 선택지를 제공합니다.

- **URL:** `POST /api/v1/chat/checklist`
- **Request Body:**
  ```json
  {
    "issue": "퇴직금",
    "situation": "편의점에서 1년 넘게 일했는데...",
    "all_qa": [], 
    "round": 1,
    "previous_rag_results": [],
    "openai_api_key": "sk-proj-..."
  }
  ```
- **Response:**
  ```json
  {
    "questions": [
       {"id": "q1", "text": "주 평균 근로시간이 15시간 이상인가요?", "options": ["네", "아니요", "모르겠음"]}
    ],
    "is_final": false,
    "rag_results": [...]
  }
  ```

### 단계 4-3: 최종 결론 도출 (Conclusion)
사용자가 답변한 사실 관계(`all_qa`)를 바탕으로 법적 결론을 내립니다.

- **URL:** `POST /api/v1/chat/conclusion`
- **Request Body:**
  ```json
  {
    "issue": "퇴직금",
    "all_qa": [
      {"q": "주 평균 근로시간이 15시간 이상인가요?", "a": "네"},
      {"q": "계속 근로기간이 1년 이상인가요?", "a": "네"}
    ],
    "stream": false, // true로 설정 시 SSE 스트리밍 응답 (text/event-stream)
    "openai_api_key": "sk-proj-..."
  }
  ```
- **Response:**
  ```json
  {
    "conclusion": "근로자퇴직급여 보장법에 따라 퇴직금 지급 대상입니다...",
    "laws": [...],
    "penalty_supplementary": "3년 이하의 징역 또는 3천만원 이하의 벌금...",
    "related_questions": ["지연 이자는 어떻게 되나요?"]
  }
  ```

---

## 5. 단답형 QA (Knowledge & Calculation)

특정 사안에 대한 긴 상담이 아닌, 법률 지식이나 계산 방법에 대한 단답형 질문을 처리합니다.

### 지식 QA
- **URL:** `POST /api/v1/chat/qa/knowledge`
- **Request Body:**
  ```json
  {
    "question": "연차휴가는 1년에 며칠 발생하나요?",
    "openai_api_key": "sk-proj-..."
  }
  ```
- **Response:**
  ```json
  {
    "answer": "근로기준법 제60조에 따라 1년간 80퍼센트 이상 출근한 근로자에게 15일의...",
    "metadata": {...}
  }
  ```

### 계산 로직 QA (수당, 퇴직금 계산법 안내)
- **URL:** `POST /api/v1/chat/qa/calculation`
- **Request Body:** `question` (필수) + 공통 파라미터 선택
- **Response:** 계산 방법 및 공식 안내 텍스트

### 서류·서식 QA
- **URL:** `POST /api/v1/chat/qa/documents`
- **Request Body:** `question` (필수, 예: "해고예보 통보서 서식이 있나요?") + 공통 파라미터 선택
- **Response:** `{ "answer": "...", "documents": [ ... ] }`

---

## 6. 법률 둘러보기

- **URL:** `GET /api/v1/laws/list` — 법령 목록
- **URL:** `GET /api/v1/laws/chapters?law_id=...&source=...` — 장 목록
- **URL:** `GET /api/v1/laws/articles/{chapter_number}?law_id=...&source=...` — 조문 목록

---

## 7. API 동작 검사 (스크립트)

배포·로컬 서버의 **모든 엔드포인트**가 정상 응답하는지 한 번에 검사할 수 있습니다.

- **스크립트:** `scripts/check_deployed_api.py`
- **실행 (배포 URL 기준):**
  ```bash
  python scripts/check_deployed_api.py
  ```
- **로컬 서버 검사:**
  ```bash
  # Windows PowerShell
  $env:LAW_API_BASE_URL="http://127.0.0.1:8000"
  python scripts/check_deployed_api.py

  # Linux/macOS
  LAW_API_BASE_URL=http://127.0.0.1:8000 python scripts/check_deployed_api.py
  ```
- **출력:** 각 엔드포인트별 `[OK]`/`[FAIL]` 및 HTTP 상태 코드, 통과/실패 개수, 주요 엔드포인트(GET /, health, invoke, classify)의 **응답 예시** JSON.

---

## 💡 개발 팁 (프론트엔드 연동)

1. **권장 플로우:** 상담은 **`POST /api/v1/chat/invoke` 한 종류만** 사용. `message`와 `thread_id`로 체크리스트·다음 턴까지 처리.
2. **상태 관리:** API 키·모델을 상태(State)나 브라우저 스토리지에 저장해 두고, 모든 POST 요청 Body에 `openai_api_key`, `model` 등을 선택적으로 주입.
3. **스트리밍 결론:** 단계별 결론(`/api/v1/chat/conclusion`)에서 `stream: true` 시 SSE(`text/event-stream`)로 수신 가능.
4. **API 명세서:** Swagger UI는 **서버 Base URL + `/docs`** (예: `https://lawchat-api.onrender.com/docs`)에서 확인.
