# LawChat API 사용 방법 (전체)

노동법 RAG 백엔드 API의 **전체 사용 방법**을 한 문서에 정리했습니다.  
실시간 명세는 **Base URL + `/docs`**(Swagger UI), **Base URL + `/openapi.json`**에서 확인할 수 있습니다.

---

## 주의 사항 (필독)

| 구분 | 내용 |
|------|------|
| **OpenAI API 키** | **서버는 OpenAI API 키를 제공하지 않습니다.** LLM을 쓰는 모든 POST 요청에 **요청 바디에 `openai_api_key`를 반드시 넣어야** 합니다. 빼면 **400** `MISSING_API_KEY` 응답. |
| **법령 API 키** | 국가법령정보(서류·법령 검색)용 키는 **요청으로 받지 않습니다.** 서버에만 **Secret `LAW_API_OC`**를 설정합니다. 서류 QA(`/api/v1/chat/qa/documents`) 사용 시 서버에 이 값이 없으면 **400** `DOCUMENTS_REQUIRES_LAW_API_KEY`. |
| **Content-Type** | 모든 POST 요청은 **`Content-Type: application/json`** 으로 보내고, 바디는 **JSON**입니다. |
| **HTTPS** | 배포 환경에서는 반드시 **HTTPS**로 호출하세요. API 키가 평문으로 노출되지 않도록 합니다. |
| **키 보관** | 브라우저/앱에 API 키를 저장하면 탈취 위험이 있습니다. 공개 웹에서는 백엔드(BFF)에서만 키를 보관하고, 프론트는 BFF를 호출하는 방식을 권장합니다. |
| **로깅** | 서버에 요청 로깅을 추가할 경우 `openai_api_key` 필드는 **반드시 마스킹** 후 로깅하세요. |
| **500 디버깅** | 서버 오류 원인 확인 시 요청 헤더에 **`X-Law-Debug: 1`** 를 넣으면 응답 `detail`에 예외 메시지가 포함됩니다. 운영 환경에서는 사용하지 마세요. |

---

## 기본 정보

| 항목 | 값 |
|------|-----|
| **Base URL** | 배포 시 예: `https://law-chat-api.onrender.com` |
| **인증** | 별도 HTTP 인증 없음. LLM 엔드포인트는 요청 바디에 `openai_api_key` 필수. |
| **Content-Type** | `application/json` (POST) |
| **추적** | 응답 헤더 `X-Request-Id` (클라이언트가 보내면 그대로 반환) |
| **Rate limit** | 서버에 `RATE_LIMIT_PER_MINUTE` 설정 시 IP당 분당 N회. 초과 시 **429** |

---

## 공통 요청 필드 (LLM 사용 POST)

LLM을 사용하는 POST 엔드포인트에서 공통으로 쓸 수 있는 필드입니다.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| **`openai_api_key`** | string | **예** | OpenAI(또는 호환) API 키. **서버는 제공하지 않음** — 매 요청마다 클라이언트가 필수로 전달. |
| `model` | string | 아니오 | 채팅 모델 (예: `gpt-4o-mini`, `gpt-4o`) |
| `openai_base_url` | string | 아니오 | OpenAI Base URL (Azure·프록시) |
| `temperature` | number | 아니오 | LLM temperature (0.0~2.0) |
| `max_tokens` | number | 아니오 | LLM 최대 출력 토큰 수 |
| `reasoning_effort` | string | 아니오 | 추론 모델(o1/o3 등): `low` \| `medium` \| `high` |
| `top_p` | number | 아니오 | LLM top_p (0.0~1.0) |
| `prompt_overrides` | object | 아니오 | 단계별 프롬프트 덮어쓰기 (아래 참고) |

---

## 에러 응답

| HTTP | code | 의미 |
|------|------|------|
| 400 | `MISSING_API_KEY` | LLM 엔드포인트에 `openai_api_key` 없음. `detail.message` 에 안내 문구 |
| 400 | `DOCUMENTS_REQUIRES_LAW_API_KEY` | 서류 QA 사용 시 서버에 `LAW_API_OC` Secret 미설정 |
| 429 | `RATE_LIMITED` | Rate limit 초과 |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류. 헤더 `X-Law-Debug: 1` 시 예외 메시지 포함 |

---

## 엔드포인트 전체 목록

### 1. GET /

**설명:** API 안내 JSON.

**요청:** 없음.

**응답 (200):**
```json
{
  "service": "LawChat Backend API",
  "docs": "/docs",
  "health": "/api/v1/health",
  "message": "API 사용법은 GET /docs 에서 확인하세요."
}
```

---

### 2. GET /api/v1/health

**설명:** 서버 상태·버전·벡터스토어 확인.

**요청:** 없음.

**응답 (200):**
```json
{
  "status": "ok",
  "version": "1.2.0",
  "context_supported": true,
  "vector_store_ready": true,
  "vector_dir_exists": true
}
```

---

### 3. GET /api/v1/laws/list

**설명:** 법령 목록.

**요청:** 없음.

**응답 (200):** 배열. 각 항목 `id`, `name`, `source` 등.

---

### 4. GET /api/v1/laws/chapters

**설명:** 특정 법령의 장(章) 목록.

**Query:** `law_id` (선택), `source` (선택)

**응답 (200):** 장 목록 배열.

---

### 5. GET /api/v1/laws/articles/{chapter_number}

**설명:** 특정 장의 조문 목록.

**Path:** `chapter_number` (string)

**Query:** `law_id`, `source` (선택)

**응답 (200):** 조문 목록 배열.

---

### 6. POST /api/v1/chat/route

**설명:** 사용자 입력의 질문 유형 분류 (지식/계산/상황/예외/서류 등).

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| text | string | 예 | 사용자 입력 문장 |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200):**
```json
{ "question_type": "knowledge" | "calculation" | "situation" | "exception" | "documents" }
```

---

### 7. POST /api/v1/chat/invoke (권장)

**설명:** **한 번의 호출로** 상담 플로우 전체 실행 (라우팅·이슈분류·체크리스트·결론·지식/계산/서류 분기). **가장 권장하는 엔드포인트.**

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| message | string | 예 | 사용자 메시지 |
| openai_api_key | string | 예 | LLM용 API 키 |
| thread_id | string | 아니오 | 대화 스레드 ID (기본 `"default"`) |
| model | string | 아니오 | 모델 |
| openai_base_url | string | 아니오 | Base URL |
| prompt_overrides | object | 아니오 | 단계별 프롬프트 덮어쓰기 |
| response_format | string | 아니오 | `markdown` \| `plain` |
| max_length | number | 아니오 | 응답 최대 문자 수 |
| language | string | 아니오 | `ko` \| `en` |
| tone | string | 아니오 | `formal` \| `casual` |
| top_k | number | 아니오 | 이슈 분류·검색 시 조문 수 (기본 22) |
| filter_sources | array | 아니오 | 검색 대상 법령 목록 |
| temperature, max_tokens, reasoning_effort, top_p | | 아니오 | 공통 |
| stream | boolean | 아니오 | true 시 SSE 스트리밍 응답 |

**응답 (200, stream=false):**

| 필드 | 설명 |
|------|------|
| status | `"ok"` |
| messages | `[{ "t": "HumanMessage"|"AIMessage", "c": "내용" }, ...]` |
| phase | `"input"` \| `"checklist"` \| `"conclusion"` |
| checklist | phase가 checklist일 때. `{ "item", "question" }` 배열 |
| selected_issue | 선택된 이슈 (예: 퇴직금) |
| situation | 정리된 상황 문장 |
| articles_by_issue | 이슈별 조문 목록 |
| checklist_rag_results | 체크리스트 생성에 사용된 RAG 결과 |
| usage | 토큰 사용량 (선택 제공) |

**참고:** 결론 텍스트는 `messages` 중 마지막 `t: "AIMessage"` 항목의 `c` 값입니다. 별도 `conclusion` 필드는 없습니다.

**2차 요청(체크리스트 답변) 시 `message` 형식:**  
`phase`가 `"checklist"`일 때, 같은 `thread_id`로 체크리스트에 대한 답변을 보내면 결론 단계로 진행됩니다. `message`는 **한 줄에 "질문: 답변"** 형태로, 여러 줄이면 줄바꿈(`\n`)으로 구분합니다.  
예: `"주 평균 15시간 이상 근로인가요?: 네\n1년 이상 근속인가요?: 아니요"`

**예시 요청:**
```json
{
  "message": "월급을 두 달째 못 받았어요",
  "thread_id": "user-123",
  "openai_api_key": "sk-proj-...",
  "model": "gpt-4o-mini"
}
```

---

### 8. POST /api/v1/chat/invoke/batch

**설명:** 여러 메시지를 순차 처리. 상위에서 `openai_api_key`, `model` 등 공통 적용.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| requests | array | 예 | `[{ "message": "...", "thread_id": "..." }]` 최대 20개 권장. 항목별 `temperature`, `max_tokens` 등 지정 가능 |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, prompt_overrides 등 | | 아니오 | 공통 |

**응답 (200):**
```json
{
  "results": [
    { "status": "ok", "result": { "status": "ok", "messages": [...], "phase": "...", ... } },
    { "status": "error", "message": "..." }
  ],
  "count": 2
}
```

---

### 9. POST /api/v1/chat/classify

**설명:** 사용자 상황 문장에서 노동법 이슈·연관 조문 추출.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| situation | string | 예 | 상황 설명 |
| top_k | number | 아니오 | 검색 조문 수 (기본 22) |
| prompt_overrides | object | 아니오 | 이슈 분류 프롬프트 덮어쓰기 (`system_issue_classification`, `user_issue_classification`) |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200):**
```json
{
  "status": "success",
  "issues": ["퇴직금", "임금"],
  "articles_by_issue": {
    "퇴직금": [{ "article": "제9조 ...", "title": "" }]
  }
}
```

---

### 10. POST /api/v1/chat/checklist

**설명:** 이슈·상황·기존 Q&A 기반 체크리스트(질문 목록) 생성.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| issue | string | 예 | 이슈 키워드 (예: 퇴직금) |
| situation | string | 예 | 상황 설명 |
| all_qa | array | 아니오 | 기존 Q&A `[{ "question", "answer" }]` |
| round | number | 아니오 | 라운드 (기본 1) |
| previous_rag_results | array | 아니오 | 이전 RAG 결과 |
| prompt_overrides | object | 아니오 | 체크리스트·연속 프롬프트 덮어쓰기 (`system_checklist`, `user_checklist`, `system_checklist_continuation`, `user_checklist_continuation`) |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200):**
```json
{
  "checklist": [{ "item": "요약 문구", "question": "주 평균 근로시간이 15시간 이상인가요?" }],
  "rag_results": [...],
  "should_continue": false,
  "continuation_reason": null,
  "issues": [...],
  "articles_by_issue": {}
}
```
실패 시(예: 컨텍스트 없음)에는 `checklist`가 빈 배열이거나 `error` 필드가 포함될 수 있습니다.

---

### 11. POST /api/v1/chat/conclusion

**설명:** 이슈 + Q&A 기반 최종 결론 생성. 스트리밍 옵션 지원.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| issue | string | 예 | 이슈 키워드 |
| all_qa | array | 예 | `[{ "question", "answer" }]` 또는 `[{ "q", "a" }]` |
| stream | boolean | 아니오 | true 시 SSE 스트리밍 (기본 false) |
| prompt_overrides | object | 아니오 | 결론 프롬프트 덮어쓰기 (`system_conclusion`, `user_conclusion`) |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200, stream=false):**
```json
{
  "conclusion": "근로자퇴직급여 보장법에 따라...",
  "related_articles": ["제9조", "제10조"],
  "penalty_supplementary": "3년 이하의 징역 또는...",
  "related_questions": ["지연 이자는 어떻게 되나요?"],
  "usage": { "prompt_tokens": 1200, "completion_tokens": 450, "total_tokens": 1650 }
}
```

---

### 12. POST /api/v1/chat/qa/knowledge

**설명:** 지식/개념 질문에 대한 RAG 기반 답변.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| question | string | 예 | 질문 |
| context | string | 아니오 | 추가 컨텍스트 |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200):**
```json
{
  "answer": "근로기준법 제60조에 따라...",
  "metadata": {
    "content": "...",
    "model": "gpt-4o-mini",
    "usage": { "prompt_tokens": 800, "completion_tokens": 200, "total_tokens": 1000 }
  }
}
```

---

### 13. POST /api/v1/chat/qa/calculation

**설명:** 수당·퇴직금 등 계산 방법/공식 안내.

**Request Body (JSON):** `question` (필수), openai_api_key (필수), model 등 공통.

**응답 (200):**
```json
{
  "answer": "퇴직금은 (평균임금 × 30일 × ...)...",
  "metadata": {
    "content": "...",
    "model": "gpt-4o-mini",
    "usage": { "prompt_tokens": 600, "completion_tokens": 350, "total_tokens": 950 }
  }
}
```

---

### 14. POST /api/v1/chat/qa/documents

**설명:** 서류·서식 관련 질문. 국가법령정보 API로 법령·행정규칙 별표·서식 목록 조회. **LLM 미사용** — `openai_api_key` 불필요. **서버 Secret `LAW_API_OC` 필요** — 미설정 시 **400** `DOCUMENTS_REQUIRES_LAW_API_KEY`.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| question | string | 예 | 질문 (예: 해고예보 서식, 퇴직금 서류) |
| context | string | 아니오 | 추가 컨텍스트 (현재 미사용) |

**응답 (200):**
```json
{
  "answer": "**'해고예보' 관련 법령·행정규칙 별표·서식**\n\n1. 해고예보서 (근로기준법)...",
  "documents": [
    { "name": "해고예보서", "law_name": "근로기준법", "source": "법령 별표·서식", "link": "https://..." }
  ]
}
```

---

### 15. GET /api/v1/prompts

**설명:** 프롬프트 커스터마이징용 **기본(기본값) 프롬프트** 조회. `prompt_overrides`에 사용하는 모든 키에 대한 현재 기본 텍스트를 반환합니다. **인증 불필요.**

**요청:** 없음.

**응답 (200):**
```json
{
  "prompts": {
    "system_issue_classification": "You are an expert at classifying...",
    "user_issue_classification": "User situation:\n<situation>\n\n[Provided legal provisions]\n<rag_context>...",
    "system_checklist": "...",
    "user_checklist": "...",
    "system_checklist_continuation": "...",
    "user_checklist_continuation": "...",
    "system_conclusion": "...",
    "user_conclusion": "...",
    "system_knowledge_qa": "...",
    "user_knowledge_qa": "...",
    "system_calculation_qa": "...",
    "user_calculation_qa": "...",
    "system_exception_qa": "...",
    "user_exception_qa": "..."
  },
  "placeholders": {
    "user_issue_classification": ["situation", "rag_context", "allowed_block(optional)"],
    "user_checklist": ["issue", "rag_context", "filtered_provisions", "already_asked_text"],
    "user_checklist_continuation": ["issue", "qa_text (Q&A 목록)", "rag_context"],
    "user_conclusion": ["issue", "qa_list", "rag_context", "related_articles_hint", "law_names_hint"],
    "user_knowledge_qa": ["question", "rag_context"],
    "user_calculation_qa": ["question", "rag_context"],
    "user_exception_qa": ["question", "rag_context"]
  },
  "usage": "prompt_overrides에 넣을 때 위 키와 동일한 이름으로 덮어쓰면 됩니다. user_* 템플릿은 플레이스홀더를 {변수명} 형태로 사용하세요."
}
```
user_* 항목은 플레이스홀더 예시(`<situation>`, `<issue>` 등)가 들어 있는 템플릿 형태로 반환됩니다. 커스텀 시 `placeholders`의 변수명을 `{변수명}` 형태로 사용하면 됩니다.

---

## LLM / 서버 Secret 요약

| 엔드포인트 | openai_api_key (요청 필수) | 서버 LAW_API_OC (Secret) |
|------------|----------------------------|---------------------------|
| GET /, /api/v1/health, /api/v1/prompts, /api/v1/laws/* | 아니오 | 아니오 |
| POST /api/v1/chat/qa/documents | 아니오 | **예** (서버 Secret 필수) |
| POST /api/v1/chat/route, invoke, invoke/batch, classify, checklist, conclusion, qa/knowledge, qa/calculation | **예** | 아니오 |

---

## 프롬프트 커스터마이징 (prompt_overrides)

요청 바디에 **`prompt_overrides`** (object)를 넣으면 해당 단계의 시스템/사용자 프롬프트를 **완전히 교체**할 수 있습니다.

**기본 프롬프트 조회:**  
커스터마이징 전 기존 프롬프트를 확인하려면 **`GET /api/v1/prompts`** 를 호출하세요.  
응답의 `prompts`에 각 키별 기본 텍스트가 들어 있고, `placeholders`에 user_* 프롬프트에서 사용하는 변수명이 안내됩니다. (인증 불필요)

**지원 키 (모두 선택):**  
`system_issue_classification`, `user_issue_classification`, `system_checklist`, `user_checklist`, `system_checklist_continuation`, `user_checklist_continuation`, `system_conclusion`, `user_conclusion`, `system_exception_qa`, `user_exception_qa`, `system_knowledge_qa`, `user_knowledge_qa`, `system_calculation_qa`, `user_calculation_qa`

**사용 가능 엔드포인트:**  
`POST /api/v1/chat/invoke`, `/api/v1/chat/classify`, `/api/v1/chat/checklist`, `/api/v1/chat/conclusion`

**user_checklist 오버라이드 시 추가 플레이스홀더:**  
`GET /api/v1/prompts`의 `placeholders.user_checklist` 외에, 실제 치환 시에는 **`situation`**, **`situation_block`**, **`already_block`**, **`tail`**, **`context`**(`rag_context`와 동일)도 사용할 수 있습니다. 템플릿에 `{...}` 형태로 넣으면 됩니다.

---

## 개발 팁

1. **권장 플로우:** 상담은 **`POST /api/v1/chat/invoke` 한 엔드포인트만** 사용. `message`와 `thread_id`로 체크리스트·다음 턴까지 처리.
2. **상태 관리:** 클라이언트에서 `openai_api_key`, `model` 등을 입력받아 저장한 뒤, LLM 호출 시 요청 바디에 `openai_api_key`(필수), `model`(선택)로 전달.
3. **스트리밍:** invoke에 `stream: true` 또는 conclusion에 `stream: true` 시 SSE(`text/event-stream`)로 수신 가능.
4. **API 명세:** Swagger UI는 **Base URL + `/docs`**, OpenAPI JSON은 **Base URL + `/openapi.json`**.
5. **샘플 스크립트:** 프로젝트 루트의 **`scripts/sample_invoke_flow.py`** 로 invoke 흐름(헬스체크 → 1차 invoke → 체크리스트 답변 → 결론)을 실행할 수 있습니다. 환경변수 `OPENAI_API_KEY`, `LAW_API_BASE_URL`(선택) 설정 후 `python scripts/sample_invoke_flow.py` 로 실행. 프롬프트 오버라이드 동작 확인은 `python scripts/sample_invoke_flow.py --test-all-overrides` 로 할 수 있습니다.

---
