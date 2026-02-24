# LawChat API 레퍼런스 (개발자 도구용)

개발자 도구·클라이언트 생성기·테스트 UI 등에서 사용할 수 있도록 엔드포인트별 요청/응답 스키마와 예시를 정리한 문서입니다.  
실시간 명세는 **Base URL + `/docs`** (Swagger UI), **Base URL + `/openapi.json`** (OpenAPI 3.0 JSON)에서 확인할 수 있습니다.

---

## 이 API 백엔드가 하는 일

**정의:** 노동법 RAG(검색 기반 생성) **오케스트레이션·파이프라인 제공** 백엔드입니다.

| 역할 | 설명 |
|------|------|
| **하는 일** | 사용자 메시지를 받아 **이슈 분류 → 체크리스트 생성 → 결론 도출** 등 단계를 조합·실행하고, 노동법 벡터 검색(RAG)·국가법령정보 API 연동·프롬프트 설계를 제공합니다. 클라이언트가 준 **API 키·모델·파라미터**로 LLM을 호출하고, **토큰 사용량(usage)**·**스트리밍**·**배치** 등 호출 방식을 지원합니다. |
| **하지 않는 일** | LLM을 직접 운영하지 않으며, **OpenAI(또는 호환) API 키를 저장·관리하지 않습니다.** 키·모델·temperature 등은 **요청마다 클라이언트가 전달**하는 BYOK(Bring Your Own Key) 방식입니다. |

한 줄로 쓰면: **“노동법 상담 플로우와 RAG를 제공하고, LLM 호출은 클라이언트가 제공한 키·설정으로 대신 실행해 주는 오케스트레이터”** 입니다.

---

## 기본 정보

| 항목 | 값 |
|------|-----|
| **Base URL** | `https://law-chat-api.onrender.com` (배포 시) |
| **인증** | 없음. LLM 엔드포인트는 요청 바디에 `openai_api_key` 필수. |
| **Content-Type** | `application/json` (POST 전용) |
| **CORS** | 허용 (기본 `*`) |
| **에러 형식** | `{"detail": "메시지"}` (400/500) |
| **추적** | 모든 응답 헤더에 `X-Request-Id` (클라이언트가 보내면 그대로 반환) |
| **Rate limit** | `RATE_LIMIT_PER_MINUTE` 환경변수 설정 시 IP당 분당 N회. 초과 시 **429** |

---

## 공통 요청 필드 (POST Body)

LLM을 사용하는 POST 엔드포인트에서 사용할 수 있는 공통 필드입니다.

| 필드 | 타입 | 필수(LLM) | 설명 |
|------|------|-----------|------|
| `openai_api_key` | string | **예** | OpenAI(또는 호환) API 키. **서버는 제공하지 않음** — 클라이언트가 매 요청에 필수. 미전달 시 **400** |
| `model` | string | 아니오 | 채팅 모델 (예: `gpt-4o-mini`, `gpt-4o`) |
| `openai_base_url` | string | 아니오 | OpenAI Base URL (Azure·프록시) |
| `temperature` | number | 아니오 | LLM temperature (0.0~2.0). 미지정 시 기본값 |
| `max_tokens` | number | 아니오 | LLM 최대 출력 토큰 수. 미지정 시 기본값 |
| `reasoning_effort` | string | 아니오 | 추론 모델(o1/o3 등)용: `low` \| `medium` \| `high` |
| `top_p` | number | 아니오 | LLM top_p (0.0~1.0). 추론 모델에는 미적용 |
| `prompt_overrides` | object | 아니오 | 단계별 프롬프트 덮어쓰기. 아래 "프롬프트 커스터마이징" 참고 |

**OpenAI API 키:** 서버에서는 **제공하지 않습니다.** LLM 사용 엔드포인트 호출 시 요청 바디에 `openai_api_key`를 반드시 넣어야 합니다.  
**법령 API(국가법령정보 OC):** 요청으로 받지 않습니다. 서버에 **Secret** `LAW_API_OC`를 설정해 두면 서류·법령 검색 등에 사용됩니다.

---

## 프롬프트 커스터마이징 (prompt_overrides)

요청 바디에 **`prompt_overrides`** (object)를 넣으면, 해당 단계의 시스템/사용자 프롬프트를 **완전히 교체**할 수 있습니다.  
개발자 도구·다른 톤·다른 언어·특정 법령 강조 등으로 **완전 커스터마이징**이 가능합니다.

**지원 키 (모두 선택):**

| 키 | 적용 단계 | 설명 |
|----|-----------|------|
| `system_issue_classification` | 이슈 분류 | 시스템 프롬프트 전체 |
| `user_issue_classification` | 이슈 분류 | 사용자 프롬프트. 플레이스홀더: `{situation}`, `{rag_context}`, `{allowed_block}` |
| `system_checklist` | 체크리스트 생성 | 시스템 프롬프트 전체 |
| `user_checklist` | 체크리스트 생성 | 사용자 프롬프트. 플레이스홀더: `{issue}`, `{rag_context}`, `{filtered_provisions}`, `{already_block}`, `{tail}` |
| `system_checklist_continuation` | 체크리스트 추가 질문 | 시스템 프롬프트 전체 |
| `user_checklist_continuation` | 체크리스트 추가 질문 | 사용자 프롬프트. 플레이스홀더: `{issue}`, `{qa_text}`, `{rag_context}` |
| `system_conclusion` | 결론 도출 | 시스템 프롬프트 전체 |
| `user_conclusion` | 결론 도출 | 사용자 프롬프트. 플레이스홀더: `{issue}`, `{qa_list}`, `{rag_context}`, `{related_articles_hint}` |
| `system_exception_qa` | 예외 QA (상황·체크리스트 외 질문) | 시스템 프롬프트 전체 |
| `user_exception_qa` | 예외 QA | 사용자 프롬프트 (플레이스홀더는 내부 사용) |
| `system_knowledge_qa` | 지식 QA (invoke 내) | 시스템 프롬프트 전체 |
| `user_knowledge_qa` | 지식 QA | 사용자 프롬프트 (플레이스홀더는 내부 사용) |
| `system_calculation_qa` | 계산 QA (invoke 내) | 시스템 프롬프트 전체 |
| `user_calculation_qa` | 계산 QA | 사용자 프롬프트 |

**사용 가능 엔드포인트:**  
`POST /api/v1/chat/invoke`, `POST /api/v1/chat/classify`, `POST /api/v1/chat/checklist`, `POST /api/v1/chat/conclusion`

**예시 (invoke 요청에 톤만 바꾸기):**
```json
{
  "message": "퇴직금을 못 받았어요",
  "openai_api_key": "sk-...",
  "prompt_overrides": {
    "system_conclusion": "You are a concise labor law advisor. Write the conclusion in 2 short paragraphs in Korean. Be direct and actionable."
  }
}
```

---

## 에러 응답

응답 본문에 **`code`** 가 포함되면 클라이언트에서 분기 처리할 수 있습니다.

| HTTP | code | 상황 |
|------|------|------|
| 400 | `MISSING_API_KEY` | LLM 엔드포인트에 `openai_api_key` 없음. `detail.message` 에 안내 문구 |
| 400 | `DOCUMENTS_REQUIRES_LAW_API_KEY` | 서류 QA 사용 시 서버에 LAW_API_OC Secret 미설정 |
| 429 | `RATE_LIMITED` | Rate limit 초과 (`RATE_LIMIT_PER_MINUTE` 설정 시) |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류. 요청 헤더 `X-Law-Debug: 1` 시 예외 메시지 포함 |

---

## 엔드포인트 목록

### 1. GET /

**설명:** API 안내 JSON.

**요청:** 쿼리/바디 없음.

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

**설명:** 서버 상태·버전·벡터스토어·의존성 확인.

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

**응답 (200):** 배열. 각 항목은 `id`, `name`, `source` 등.

---

### 4. GET /api/v1/laws/chapters

**설명:** 특정 법령의 장(章) 목록.

**Query:**

| 이름 | 타입 | 필수 | 설명 |
|------|------|------|------|
| law_id | string | 아니오 | 법령 ID |
| source | string | 아니오 | 출처 (law 등) |

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
| model | string | 아니오 | 모델 오버라이드 |
| openai_base_url | string | 아니오 | Base URL |

**응답 (200):**
```json
{
  "question_type": "knowledge" | "calculation" | "situation" | "exception" | "documents"
}
```

---

### 7. POST /api/v1/chat/invoke

**설명:** 한 번의 호출로 상담 플로우 전체 실행 (라우팅·이슈분류·체크리스트·결론·지식/계산/서류 분기). **권장 엔드포인트.**

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| message | string | 예 | 사용자 메시지 |
| thread_id | string | 아니오 | 대화 스레드 ID (기본 `"default"`) |
| openai_api_key | string | 예 | LLM용 API 키 |
| model | string | 아니오 | 모델 |
| openai_base_url | string | 아니오 | Base URL |
| prompt_overrides | object | 아니오 | 단계별 프롬프트 덮어쓰기 |
| response_format | string | 아니오 | `markdown` \| `plain`. 기본 markdown |
| max_length | number | 아니오 | 응답 메시지 최대 문자 수. 초과 시 잘림 |
| language | string | 아니오 | `ko` \| `en`. 응답 언어 |
| tone | string | 아니오 | `formal` \| `casual`. 톤 |
| top_k | number | 아니오 | 이슈 분류·검색 시 조문 수 (기본 22) |
| filter_sources | array | 아니오 | 검색 대상 법령 목록. 비우면 전체 노동법 (예: `["근로기준법(법률)"]`) |
| temperature | number | 아니오 | LLM temperature (공통 필드) |
| max_tokens | number | 아니오 | LLM 최대 출력 토큰 (공통 필드) |
| reasoning_effort | string | 아니오 | 추론 모델용 (공통 필드) |
| top_p | number | 아니오 | LLM top_p (공통 필드) |
| stream | boolean | 아니오 | true 시 SSE 스트리밍 응답 (마지막 AI 메시지 청크 + done 메타데이터) |

**응답 (200, stream=false):**

| 필드 | 타입 | 설명 |
|------|------|------|
| status | string | `"ok"` |
| messages | array | `{ "t": "HumanMessage" | "AIMessage", "c": "내용" }` 배열 |
| phase | string | `"input"` \| `"checklist"` \| `"conclusion"` |
| checklist | array | phase가 checklist일 때. 항목: `{ "item", "question" }` |
| selected_issue | string | 선택된 이슈 (예: 퇴직금) |
| situation | string | 정리된 상황 문장 |
| articles_by_issue | object | 이슈별 조문 목록 |
| checklist_rag_results | array | 체크리스트 생성에 사용된 RAG 결과 |

**응답 (stream=true):** `Content-Type: text/event-stream`. 각 줄은 `data: <JSON>` 형식. `type: "chunk"` 이벤트에 `content`(일부 텍스트), 마지막에 `type: "done"` 이벤트에 `phase`, `usage`, `messages` 등 메타데이터 포함.

**참고:** 결론 텍스트는 `messages` 중 마지막 `t: "AIMessage"` 항목의 `c` 값입니다. 별도 `conclusion` 필드는 없습니다.

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

### 7-1. POST /api/v1/chat/invoke/batch

**설명:** 여러 메시지를 순차 처리. 상위에서 `openai_api_key`, `model` 등 공통 적용.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| requests | array | 예 | `[{ "message": "...", "thread_id": "...", "temperature": 0.3, "max_tokens": 1500 }]`. 최대 20개 권장. 항목별 `temperature`, `max_tokens`, `reasoning_effort`, `top_p` 지정 가능 |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, prompt_overrides 등 | | 아니오 | 공통 필드 |

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

**참고:** invoke에 `stream: true` 를 넣으면 SSE로 마지막 AI 메시지가 청크 단위로 전송됩니다.

---

### 8. POST /api/v1/chat/classify

**설명:** 사용자 상황 문장에서 노동법 이슈·연관 조문 추출.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| situation | string | 예 | 상황 설명 |
| top_k | number | 아니오 | 검색 조문 수 (기본 22) |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200):**
```json
{
  "status": "success",
  "issues": ["퇴직금", "임금"],
  "articles_by_issue": {
    "퇴직금": [
      { "article": "제9조 퇴직금의 지급 등", "title": "" }
    ]
  }
}
```

---

### 9. POST /api/v1/chat/checklist

**설명:** 이슈·상황·기존 Q&A 기반 체크리스트(질문 목록) 생성.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| issue | string | 예 | 이슈 키워드 (예: 퇴직금) |
| situation | string | 예 | 상황 설명 |
| all_qa | array | 아니오 | 기존 Q&A `[{ "question", "answer" }]` |
| round | number | 아니오 | 라운드 (기본 1) |
| previous_rag_results | array | 아니오 | 이전 RAG 결과 |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200):**
```json
{
  "checklist": [
    { "item": "요약 문구", "question": "주 평균 근로시간이 15시간 이상인가요?" }
  ],
  "rag_results": [...],
  "should_continue": false,
  "continuation_reason": null,
  "issues": [...],
  "articles_by_issue": {...},
  "source": "llm",
  "debug_info": {}
}
```

---

### 10. POST /api/v1/chat/conclusion

**설명:** 이슈 + Q&A 기반 최종 결론 생성. 스트리밍 옵션 지원.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| issue | string | 예 | 이슈 키워드 |
| all_qa | array | 예 | `[{ "question", "answer" }]` 또는 `[{ "q", "a" }]` |
| stream | boolean | 아니오 | true 시 SSE 스트리밍 (기본 false) |
| openai_api_key | string | 예 | LLM용 API 키 |
| model, openai_base_url | | 아니오 | 공통 |

**응답 (200, stream=false):**
```json
{
  "conclusion": "근로자퇴직급여 보장법에 따라...",
  "related_articles": ["제9조", "제10조"],
  "penalty_supplementary": "3년 이하의 징역 또는...",
  "related_questions": ["지연 이자는 어떻게 되나요?"],
  "usage": {
    "prompt_tokens": 1200,
    "completion_tokens": 450,
    "total_tokens": 1650
  }
}
```
- **usage:** 결론 생성 LLM 호출 1회 기준 토큰 사용량. (stream=true일 때는 없음)

**응답 (stream=true):** `Content-Type: text/event-stream`, 청크 단위 텍스트.

---

### 11. POST /api/v1/chat/qa/knowledge

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
    "usage": {
      "prompt_tokens": 800,
      "completion_tokens": 200,
      "total_tokens": 1000
    }
  }
}
```
- **metadata.usage:** 해당 LLM 호출 1회의 토큰 사용량.

---

### 12. POST /api/v1/chat/qa/calculation

**설명:** 수당·퇴직금 등 계산 방법/공식 안내.

**Request Body (JSON):** `question` (필수), 공통 필드.

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
- **metadata.usage:** 해당 LLM 호출 1회의 토큰 사용량.

---

### 13. POST /api/v1/chat/qa/documents

**설명:** 서류·서식 관련 질문. 국가법령정보 **licbyl/admbyl** API로 법령·행정규칙 별표·서식 목록 조회. **LLM 미사용** — `openai_api_key` 불필요. **서버 Secret `LAW_API_OC`(국가법령정보 OC) 필요** — 미설정 시 **400** `DOCUMENTS_REQUIRES_LAW_API_KEY`.

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| question | string | 예 | 질문 (예: 해고예보 서식, 퇴직금 서류) |
| context | string | 아니오 | 추가 컨텍스트 (현재 미사용) |

**응답 (200):**
```json
{
  "answer": "**'해고예보' 관련 법령·행정규칙 별표·서식**\n\n1. 해고예보서 (근로기준법) - 법령 별표·서식\n\n※ 상세 서식 파일은 국가법령정보센터(www.law.go.kr)에서...",
  "documents": [
    { "name": "해고예보서", "law_name": "근로기준법", "source": "법령 별표·서식", "link": "https://..." }
  ]
}
```
- **documents**: `name`(서식명), `law_name`(관련 법령명), `source`(법령/행정규칙 구분), `link`(PDF 등 링크, 있을 경우).

**에러 (400):** `code: "DOCUMENTS_REQUIRES_LAW_API_KEY"` — 서버에 LAW_API_OC Secret 설정 필요.

---

## LLM 사용 여부 요약

| 엔드포인트 | openai_api_key 필요 | 서버 LAW_API_OC(Secret) |
|------------|----------------------|---------------------------|
| GET /, /api/v1/health, /api/v1/laws/* | 아니오 | 아니오 |
| POST /api/v1/chat/qa/documents | 아니오 | **예** (서버 Secret 필수) |
| POST /api/v1/chat/route, invoke, classify, checklist, conclusion, qa/knowledge, qa/calculation | **예** |

---

## 디버깅

- **500 원인 확인:** 요청 헤더에 `X-Law-Debug: 1` 추가 시, 응답 `detail`에 서버 예외 메시지 포함.
- **OpenAPI JSON:** `GET {Base URL}/openapi.json` 으로 스키마 다운로드 가능 (도구 연동용).

이 문서는 `API_USAGE.md`와 함께 참고하면 됩니다. 실제 스키마는 `/docs` 또는 `/openapi.json`을 기준으로 하세요.
