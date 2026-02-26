# 개발자 도구 구현 계획 — API 활용 설계

내가 이 개발자 도구(프롬프트 실험 도구)를 만든다면 세우는 계획과 API 활용 방식을 정리한 문서다.  
기존 `PROMPT_PLAYGROUND_PLAN.md`를 전제로, **구현 관점**에서 구체화한 것이다.

---

## 1. 도구의 위치와 목표

- **역할:** LawChat API를 호출해, 단계별·유형별로 **입력과 프롬프트를 바꿔가며** 결과를 나란히 비교하는 **프론트 전용** 도구.
- **백엔드:** 새로 두지 않는다. LawChat API(Base URL + openai_api_key)만 사용한다.
- **사용자:** 프롬프트/시나리오를 튜닝하는 개발자. API 키를 직접 넣을 수 있다고 가정한다.

---

## 2. 화면·플로우 설계

### 2.1 전체 구조

1. **설정**
   - Base URL, openai_api_key 입력·저장(로컬 스토리지 또는 env).
   - "연결 확인" 시 `GET /api/v1/health` 호출.

2. **실험 모드 선택**
   - 탭 또는 드롭다운: **의도 분류 | 이슈 분류 | 체크리스트 | 결론 | 지식 | 계산 | 예외 | 문서**.
   - 선택한 모드에 따라 **입력 폼**과 **호출할 API**가 바뀐다.

3. **입력 정의**
   - **단일 입력:** 텍스트 필드 1개(또는 JSON 에디터 1개)로 한 세트만 정의.
   - **다중 입력:** "입력 추가"로 여러 세트(예: situation 3개, message 5개) 정의. 각 행에 이름(라벨) 부여 가능.
   - **시나리오 불러오기(선택):** 로컬에 저장해 둔 시나리오(issue, all_qa 등)를 불러와 해당 단계 입력으로 채운다.

4. **프롬프트 세트**
   - "기본값 불러오기" → `GET /api/v1/prompts` 호출해 현재 단계에 해당하는 키만 필터해 표시.
   - 사용자가 system_* / user_* 텍스트 수정 후 "세트 저장" → 이름 부여해 로컬에 저장. 여러 세트(기본, A, B, 짧은 버전 등) 관리.
   - 실험 시: "사용할 세트"를 1개 이상 선택. 각 세트당 1회 이상 호출(같은 입력 + 세트 A, 같은 입력 + 세트 B … 또는 입력마다 × 세트마다 조합).

5. **실행·비교**
   - "실험 실행" 클릭 시, 정의한 **입력 × 프롬프트 세트** 조합만큼 API 호출(순차 또는 병렬 제한 두고).
   - 결과를 **테이블 또는 카드**로 나란히 표시: 열 = 입력 또는 세트, 행 = 세트 또는 입력. 선택한 모드에 따라 "한 셀"에 들어갈 내용이 다름(아래 API별 출력 참고).
   - 각 셀: 복사, 펼치기/접기, JSON 보기, 내보내기(텍스트/JSON).

### 2.2 모드별 입력 폼·출력

| 모드 | 입력 UI | 호출 API | 응답에서 셀에 넣을 값 |
|------|----------|-----------|------------------------|
| 의도 분류 | message(text) 1개 또는 N개 | POST /api/v1/chat/route | `question_type` |
| 이슈 분류 | situation, top_k(선택). N개 세트 가능 | POST /api/v1/chat/classify | issues, articles_by_issue (요약 또는 펼침) |
| 체크리스트 | issue, situation, all_qa(에디터), round 등. N개 세트 | POST /api/v1/chat/checklist | checklist (질문 목록) |
| 결론 | issue, all_qa(에디터). N개 세트 | POST /api/v1/chat/conclusion | conclusion 텍스트, related_articles 등 |
| 지식 | message 1개 또는 N개 | POST /api/v1/chat/invoke | messages 중 마지막 AIMessage.c |
| 계산 | message 1개 또는 N개 | POST /api/v1/chat/invoke | 위와 동일 |
| 예외 | message 1개 또는 N개 | POST /api/v1/chat/invoke | 위와 동일 |
| 문서 | message 1개 또는 N개 | POST /api/v1/chat/invoke | 위와 동일 |

- 지식/계산/예외/문서: invoke 호출 시 **매 요청마다 서로 다른 thread_id**(예: `playground-{mode}-{timestamp}-{index}`)를 넣어서 턴이 섞이지 않게 한다.

---

## 3. API 호출 방식 (구체)

### 3.1 공통

- **Base URL:** 설정에서 저장한 값. 예: `https://law-chat-api.onrender.com`.
- **헤더:** `Content-Type: application/json`.
- **모든 LLM API 요청 바디:** 최소한 `openai_api_key` 포함. 선택: `model`, `temperature`, `max_tokens` 등.
- **타임아웃:** 60초 이상 권장. invoke/classify/checklist/conclusion은 수십 초 걸릴 수 있음.
- **에러 처리:** 4xx/5xx 시 응답 본문(detail) 표시. `X-Law-Debug: 1` 붙이면 서버가 예외 메시지 더 돌려줄 수 있음.

### 3.2 의도 분류

- **URL:** `POST {baseUrl}/api/v1/chat/route`
- **Body:** `{ "text": "<message>", "openai_api_key": "<key>", "model": "gpt-4o-mini" }` (model 선택)
- **응답:** `{ "question_type": "knowledge" | "calculation" | "documents" | "exception" | "situation" }`
- **활용:** 입력 message 1개당 1회 호출. 여러 message면 순차 호출 후 결과를 테이블로 정리(입력 라벨 | question_type).

### 3.3 이슈 분류

- **URL:** `POST {baseUrl}/api/v1/chat/classify`
- **Body:**  
  `{ "situation": "<상황 텍스트>", "top_k": 22, "openai_api_key": "<key>", "prompt_overrides": { "system_issue_classification": "...", "user_issue_classification": "..." } }`
- **응답:** `{ "issues": [...], "articles_by_issue": { "<issue>": [{ "article", "title" }, ...] } }`
- **활용:** 입력 세트(situation 등)마다, 사용한 프롬프트 세트마다 1회 호출. 셀에는 issues 요약 + articles_by_issue 펼침/접기.

### 3.4 체크리스트

- **URL:** `POST {baseUrl}/api/v1/chat/checklist`
- **Body:**  
  `{ "issue": "...", "situation": "...", "all_qa": [{ "question": "...", "answer": "..." }], "round": 1, "previous_rag_results": [], "openai_api_key": "<key>", "prompt_overrides": { "system_checklist": "...", "user_checklist": "...", ... } }`
- **응답:** step2 결과 구조. 비교용으로는 `checklist` 배열(각 항목 question/item)만 셀에 넣어도 됨.
- **활용:** 입력 조합(issue, situation, all_qa 등) × 프롬프트 세트별로 1회 호출.

### 3.5 결론

- **URL:** `POST {baseUrl}/api/v1/chat/conclusion`
- **Body:**  
  `{ "issue": "...", "all_qa": [...], "openai_api_key": "<key>", "prompt_overrides": { "system_conclusion": "...", "user_conclusion": "..." } }`
- **응답:** conclusion 텍스트, related_articles, related_questions 등. 셀에는 conclusion + related_articles 요약.
- **활용:** issue+all_qa 세트 × 프롬프트 세트별로 1회 호출.

### 3.6 지식 / 계산 / 예외 / 문서 (invoke)

- **URL:** `POST {baseUrl}/api/v1/chat/invoke`
- **Body:**  
  `{ "message": "<질문>", "thread_id": "<매 호출 고유값>", "openai_api_key": "<key>", "prompt_overrides": { "system_knowledge_qa": "...", "user_knowledge_qa": "..." } }`  
  (지식은 knowledge_qa, 계산은 calculation_qa, 예외는 exception_qa. 문서는 현재 override 없음.)
- **thread_id:** 호출마다 새로 생성. 예: `playground-invoke-${Date.now()}-${index}`.
- **응답:** `{ "messages": [ { "t": "HumanMessage", "c": "..." }, { "t": "AIMessage", "c": "..." } ], "phase", "checklist", ... }`  
  → 셀에는 `messages` 중 마지막 `t === "AIMessage"`인 항목의 `c`.
- **활용:** message 1개당 1회(또는 프롬프트 세트당 1회). 여러 message × 여러 세트면 조합만큼 호출.

### 3.7 프롬프트 기본값 조회

- **URL:** `GET {baseUrl}/api/v1/prompts` (API 키 불필요)
- **응답:** `{ "prompts": { "system_issue_classification": "...", "user_issue_classification": "...", ... }, "placeholders": { ... }, "usage": "..." }`
- **활용:** 앱 로드 시 또는 "기본값 불러오기" 클릭 시 1회 호출. 현재 모드에 맞는 키만 필터해 에디터에 채움. placeholders는 도움말로 표시.

### 3.8 시나리오 수집(선택)

- **URL:** `POST {baseUrl}/api/v1/chat/invoke`
- **Body:**  
  1) 상황 메시지: `{ "message": "<상황>", "thread_id": "<고정 UUID>", "openai_api_key": "<key>" }`  
  2) phase가 "checklist"면 체크리스트 표시 후, 사용자가 답변을 "[질문1]: 네\n[질문2]: 아니요" 형태로 입력하면 같은 thread_id로 한 번 더 invoke.
- **응답에서 추출:** `selected_issue`, `all_qa`(또는 qa_list), `situation` 등. 이걸 "시나리오"로 저장해 두고, 체크리스트/결론 실험 시 입력으로 불러온다.

---

## 4. 데이터 저장(로컬)

- **설정:** baseUrl, openai_api_key → localStorage 또는 환경변수(도구가 Electron/로컬 서버면 env).
- **프롬프트 세트:** `{ name, keys: { system_xxx: "...", user_xxx: "..." } }[]` → localStorage 또는 JSON 파일 내보내기/가져오기.
- **시나리오:** `{ name, createdAt, situation?, issue?, all_qa?, ... }` → localStorage 또는 JSON 파일.
- **실험 결과:** 마지막 실행분만 메모리 유지. "내보내기" 시 JSON/텍스트로 저장.

---

## 5. 구현 순서(내가 택할 경우)

1. **설정 화면 + Health 체크**  
   Base URL, API 키 입력·저장, GET /api/v1/health 호출로 연동 확인.

2. **GET /api/v1/prompts 연동**  
   기본 프롬프트 불러오기, 단계별 키 매핑(의도 분류는 프롬프트 없음, 이슈 분류는 issue_classification, …).

3. **의도 분류 모드**  
   message 입력(1개 또는 여러 개) → POST /api/v1/chat/route 반복 호출 → question_type 테이블 표시. 가장 단순해서 먼저 완성.

4. **결론 모드**  
   issue, all_qa 입력(수동 또는 시나리오 불러오기) + 프롬프트 세트 1개 이상 → POST /api/v1/chat/conclusion 반복 → conclusion 나란히 비교. 입력 필드가 적어서 두 번째로 완성하기 좋음.

5. **이슈 분류 모드**  
   situation(+ top_k) + 프롬프트 세트 → POST /api/v1/chat/classify 반복 → issues, articles_by_issue 비교.

6. **체크리스트 모드**  
   issue, situation, all_qa 등 + 프롬프트 세트 → POST /api/v1/chat/checklist 반복 → checklist 비교.

7. **지식/계산/예외/문서 모드**  
   message + 프롬프트 세트, thread_id 매번 새로 생성 → POST /api/v1/chat/invoke 반복 → 마지막 AIMessage.c 비교.

8. **시나리오 캡처(선택)**  
   invoke 1~2회 플로우로 situation → checklist 답변까지 진행해 selected_issue, all_qa 저장. 체크리스트/결론 실험에 재사용.

9. **다중 입력 + 비교 뷰 공통화**  
   "입력 N개 × 프롬프트 세트 M개" 조합 실행, 단계별 출력 구조에 맞춰 테이블/카드 레이아웃, 복사·내보내기.

10. **에러·로딩·재시도**  
    타임아웃, 4xx/5xx 메시지 표시, 실패한 호출만 재시도 버튼 등.

---

## 6. 기술 스택 가정

- **프론트:** React 또는 Vue + TypeScript. 상태는 단순히 useState/전역 하나로 충분. API 호출은 fetch 또는 axios.
- **스타일:** Tailwind 또는 비슷한 유틸리티. 비교 뷰는 그리드/테이블 위주.
- **저장:** localStorage + 필요 시 JSON 파일 내보내기/가져오기. 별도 DB 없음.

---

## 7. 요약

- **API만 사용:** 새 백엔드 없이 LawChat Base URL + openai_api_key로 모든 호출.
- **모드별로 호출 API 1:1:** 의도 분류 → route, 이슈 분류 → classify, 체크리스트 → checklist, 결론 → conclusion, 지식/계산/예외/문서 → invoke(thread_id 매번 새로).
- **입력·프롬프트 모두 가변:** 고정 입력 + 여러 프롬프트 세트, 또는 여러 입력 + 같은/다른 프롬프트 세트 조합으로 실행해 결과를 나란히 비교.
- **프롬프트:** GET /api/v1/prompts로 기본값 로드 후, 세트별로 수정해 prompt_overrides로 전달.
- **구현 순서:** 설정·prompts → 의도 분류 → 결론 → 이슈 분류 → 체크리스트 → invoke 4종 → 시나리오·다중입력·비교 뷰·에러 처리.

이렇게 하면 기존 API 계약만 지키면서, 개발자 도구를 단계적으로 구현할 수 있다.
