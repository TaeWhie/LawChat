# LawChat API 사용 시 다른 AI에게 전달할 프롬프트

아래 블록 전체를 복사해, LawChat API를 사용하도록 도와줄 다른 AI(어시스턴트/에이전트)에게 붙여넣어 주세요.

---

## 복사용 프롬프트 (아래부터 끝까지)

```
당신은 LawChat 노동법 RAG API를 호출하는 코드나 플로우를 작성할 때 아래 규칙을 반드시 지켜 주세요.

【1】 Base URL
- 기본: https://law-chat-api.onrender.com
- 모든 경로는 이 Base URL 뒤에 붙인다. (예: GET /api/v1/health → https://law-chat-api.onrender.com/api/v1/health)

【2】 API 키는 서버에 없음 — 반드시 요청 바디로 보내기
- 이 API 서버에는 OPENAI_API_KEY 환경변수가 설정되어 있지 않다.
- LLM을 쓰는 엔드포인트를 호출할 때는 **호출하는 쪽(클라이언트)**이 요청 바디에 **openai_api_key**를 **필수**로 포함해야 한다. 빼면 400 에러가 난다.
- model은 선택(예: gpt-4o-mini). 안 보내면 서버 기본값 사용.

【3】 LLM 사용 엔드포인트 (openai_api_key 필수)
- POST /api/v1/chat/route
- POST /api/v1/chat/invoke  ← 상담 한 번에 처리할 때 권장
- POST /api/v1/chat/classify
- POST /api/v1/chat/checklist
- POST /api/v1/chat/conclusion
- POST /api/v1/chat/qa/knowledge
- POST /api/v1/chat/qa/calculation

위 엔드포인트 호출 시 JSON 바디에 반드시 포함: "openai_api_key": "sk-..." (그리고 필요 시 "model": "gpt-4o-mini" 등)

【4】 LLM 미사용 엔드포인트 (키 불필요)
- GET /
- GET /api/v1/health
- GET /api/v1/laws/list
- GET /api/v1/laws/chapters
- GET /api/v1/laws/articles/{chapter_number}
- POST /api/v1/chat/qa/documents

【5】 invoke 권장 사용법
- 상담은 보통 **POST /api/v1/chat/invoke** 한 종류만 쓰면 된다.
- Body 예: { "message": "퇴직금이 뭐예요?", "thread_id": "대화ID", "openai_api_key": "sk-...", "model": "gpt-4o-mini" }
- 같은 대화를 이어가려면 thread_id를 고정해서 보낸다.
- 응답: status, phase("input"|"checklist"|"conclusion"), messages(각 항목은 t: "HumanMessage"|"AIMessage", c: 내용), checklist, selected_issue 등.

【6】 결론(conclusion) 내용 위치
- invoke 응답에 "conclusion" 필드는 없다. 결론 텍스트는 **messages** 배열 안 마지막 **AIMessage**의 **c** 값이다.

【7】 체크리스트 항목 형식
- checklist 배열의 각 항목은 **item**, **question** 키를 가진다. (id, text, options는 없을 수 있음.) 표시할 문구는 question 또는 item을 쓰면 된다.

【8】 에러 처리
- openai_api_key 없이 LLM 엔드포인트 호출 → 400, detail에 "요청 바디에 openai_api_key(필수)를 넣어 주세요" 안내.
- 500 발생 시 원인 확인: 요청 헤더에 **X-Law-Debug: 1**을 넣으면 응답 detail에 서버 예외 메시지가 포함된다.

【9】 기타
- Content-Type: application/json
- 반드시 HTTPS로 호출
- 타임아웃: invoke 등 LLM 호출은 수십 초 걸릴 수 있으므로 60초 이상 권장
```

---

위 프롬프트만 전달해도 다른 AI가 LawChat API를 올바르게 호출하는 코드/플로우를 작성할 수 있습니다.

- **사용자용 요약:** 같은 폴더의 `API_USAGE.md`
- **개발자 도구·클라이언트 생성용 상세 스키마:** `API_REFERENCE.md` (엔드포인트별 Request/Response 필드, 타입, 예시)
