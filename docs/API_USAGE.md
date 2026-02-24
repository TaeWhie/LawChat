# LawChat 백엔드 API 사용 가이드

본 문서는 Render에 배포된 LawChat API의 주요 엔드포인트와 사용 방법을 안내합니다.

**서버 Base URL:** Render에 배포한 뒤 **Render 대시보드 → 해당 Web Service → 상단에 표시되는 URL**을 사용합니다. 예: `https://law-chat-api.onrender.com/`

---

## 🔑 API 사용자가 키·모델을 넣는 방식 (서버에 키 설정 불필요)

**서버에는 `OPENAI_API_KEY`를 설정하지 않습니다.**  
LLM을 쓰는 API는 **호출하는 쪽(API 사용자)**이 요청 바디에 다음을 넣습니다.

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| **`openai_api_key`** | string | **LLM API 필수** | OpenAI(또는 호환) API 키. 미전달 시 400 응답 |
| **`model`** | string | 선택 | 사용할 채팅 모델 (예: `gpt-4o`, `gpt-4o-mini`) |
| `openai_base_url` | string | 선택 | OpenAI Base URL (Azure·프록시 등) |
| `temperature` | number | 선택 | LLM temperature (0.0~2.0). 미지정 시 기본값 |
| `max_tokens` | number | 선택 | LLM 최대 출력 토큰 수 |
| `reasoning_effort` | string | 선택 | 추론 모델(o1/o3)용: `low` \| `medium` \| `high` |

**LLM 사용 엔드포인트:** `POST /api/v1/chat/route`, `/api/v1/chat/invoke`, `/api/v1/chat/classify`, `/api/v1/chat/checklist`, `/api/v1/chat/conclusion`, `/api/v1/chat/qa/knowledge`, `/api/v1/chat/qa/calculation` → 위 엔드포인트 호출 시 요청 바디에 **`openai_api_key` 필수**, **`model` 선택**.

모든 POST API 요청은 JSON 요청 바디(`application/json`)를 사용합니다.

---

## 🔑 전역 공통 파라미터 (요청 바디)

**LLM을 쓰는 POST**에서는 아래를 요청 바디에 포함합니다.

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `openai_api_key` | string | **(LLM API 필수)** OpenAI(또는 호환) API 키 |
| `model` | string | **(선택)** 채팅 모델 (예: `gpt-4o`, `gpt-4o-mini`) |
| `openai_base_url` | string | (선택) OpenAI Base URL |
| `temperature` | number | (선택) LLM temperature. `max_tokens`, `reasoning_effort`도 요청별 지정 가능 |

**법령 API(국가법령정보 OC):** 요청으로 받지 않습니다. 서류·법령 검색이 필요하면 서버에 **Secret** `LAW_API_OC`를 설정합니다.

**토큰 사용량(usage):** `POST /api/v1/chat/conclusion`(stream=false), `POST /api/v1/chat/qa/knowledge`, `POST /api/v1/chat/qa/calculation` 응답에 **`usage`** (`prompt_tokens`, `completion_tokens`, `total_tokens`)가 포함됩니다. invoke는 여러 단계 호출 합산이 필요하면 응답의 `usage` 필드를 참고하세요.

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

## 1-1. 디버깅 (500 에러 원인 확인)

API가 500을 반환할 때 **실제 예외 메시지**를 응답에 포함해 보려면, 해당 요청에 다음 헤더를 붙입니다. (재배포 불필요)

- **헤더:** `X-Law-Debug: 1`

예: `curl -X POST ... -H "X-Law-Debug: 1" -d '{"situation":"..."}'`  
응답 `detail`에 서버에서 발생한 예외 문자열이 함께 내려옵니다. 운영 환경에서는 보안상 해당 헤더 없이 호출하는 것을 권장합니다.

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
  - `openai_api_key` (필수): API 사용자 본인의 OpenAI API 키
  - `model` (선택): 사용할 모델 (예: `gpt-4o-mini`, `gpt-4o`)
  - `thread_id` (선택): 대화 스레드 ID (기본 `"default"`)
  - `openai_base_url` (선택)
  - `temperature`, `max_tokens`, `reasoning_effort` (선택): 모델 파라미터
  - `filter_sources` (선택): 검색 대상 법령 목록. 비우면 전체 노동법 (예: `["근로기준법(법률)"]`)

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
    "checklist_rag_results": [ ... ],
    "usage": { "prompt_tokens": 1200, "completion_tokens": 450, "total_tokens": 1650 }
  }
  ```
  `usage`는 전체 invoke에서 사용된 토큰 합산(선택 제공). 체크리스트 후 다음 사용자 답변을 보낼 때도 같은 `thread_id`로 `message`만 바꿔서 다시 `POST /api/v1/chat/invoke` 호출하면 됩니다.

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
    "related_questions": ["지연 이자는 어떻게 되나요?"],
    "usage": { "prompt_tokens": 1200, "completion_tokens": 450, "total_tokens": 1650 }
  }
  ```
  `usage`: 결론 생성 LLM 호출 1회 기준 토큰 사용량 (stream=true일 때는 없음).

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
    "metadata": { "content": "...", "model": "gpt-4o-mini", "usage": { "prompt_tokens": 800, "completion_tokens": 200, "total_tokens": 1000 } }
  }
  ```
  `metadata.usage`: 해당 LLM 호출의 토큰 사용량.

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

## 🔒 보안 고려사항 (API 키를 요청으로 보낼 때)

| 구간 | 상태 | 비고 |
|------|------|------|
| **전송** | ✅ | 반드시 **HTTPS**로 호출. 키가 평문으로 노출되지 않음 (Render 기본 HTTPS). |
| **서버** | ✅ | 키는 요청 처리 중 **메모리에서만** 사용하며, **저장·로그에 남기지 않음**. 400/500 응답 `detail`에도 키가 포함되지 않음. |
| **클라이언트** | ⚠️ | 브라우저/앱에서 키를 저장하면 XSS·피싱 시 탈취 가능. **공개 웹 프론트**에서는 가능하면 본인 백엔드(BFF)에서만 키를 보관하고, 프론트는 BFF를 호출하는 방식 권장. |

- **우리 서버 코드:** 요청 바디 전체를 로그로 남기지 않으며, 예외 메시지(`str(e)`)만 출력. OpenAI 클라이언트는 키를 예외 메시지에 넣지 않음.
- **운영 시:** 서버에 요청 로깅을 추가할 경우 `openai_api_key` 필드는 **반드시 마스킹** 후 로깅할 것.

---

## 💡 개발 팁 (프론트엔드 연동)

1. **권장 플로우:** 상담은 **`POST /api/v1/chat/invoke` 한 종류만** 사용. `message`와 `thread_id`로 체크리스트·다음 턴까지 처리.
2. **상태 관리:** API 사용자가 키·모델을 입력하면, 해당 값을 상태(State)나 브라우저 스토리지에 저장해 두고 LLM 호출 시 요청 Body에 `openai_api_key`(필수), `model`(선택)로 전달.
3. **스트리밍 결론:** 단계별 결론(`/api/v1/chat/conclusion`)에서 `stream: true` 시 SSE(`text/event-stream`)로 수신 가능.
4. **API 명세서:** Swagger UI는 **서버 Base URL + `/docs`** (예: `https://lawchat-api.onrender.com/docs`)에서 확인.
