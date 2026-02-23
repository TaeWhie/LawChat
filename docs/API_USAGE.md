# LawChat 백엔드 API 사용 가이드

본 문서는 Render에 배포된 LawChat API의 주요 엔드포인트와 사용 방법을 안내합니다.

**서버 Base URL:** `https://law-chat-api.onrender.com`

모든 API 요청은 JSON 요청 바디(`application/json`)를 사용합니다.

---

## 🔑 전역 공통 파라미터 (동적 API 키 주입)

사용자가 자신의 API 키를 통해 비용을 지불하고 모델을 선택할 수 있도록, **모든 POST 요청 바디**에 다음 환경 변수를 선택적으로 포함할 수 있습니다.
이 값을 넘기지 않으면 서버에 기본 설정된(혹은 더미) 키가 사용됩니다.

- `openai_api_key` (string, 선택): 사용자의 OpenAI API 키
- `law_api_key` (string, 선택): 공공데이터포털 법률 API 키 (선택 사항)

---

## 1. 서버 헬스체크 및 버전 확인

서버가 정상적으로 구동 중인지, 현재 배포된 버전을 확인합니다.

- **URL:** `GET /api/v1/health`
- **응답 예시:**
  ```json
  {
    "status": "ok",
    "version": "1.1.0-absolute-keys-v5",
    "context_supported": true
  }
  ```

---

## 2. 질문 라우팅 (의도 파악)

사용자의 입력이 어떤 유형의 질문인지(지식, 계산, 문서, 일반 등) 판별합니다.

- **URL:** `POST /api/v1/chat/route`
- **Request Body:**
  ```json
  {
    "text": "연장 수당은 어떻게 계산하나요?",
    "openai_api_key": "sk-proj-..."
  }
  ```
- **Response:**
  ```json
  {
    "question_type": "calculation_qa" // "knowledge_qa", "exception_qa", "document_qa", "general" 등
  }
  ```

---

## 3. 노동법 RAG 파이프라인 (3단계)

LawChat의 핵심인 사안 분류 -> 체크리스트 -> 최종 결론 3단계 프로세스입니다.

### 단계 3-1: 사안 분류 (Issue Classification)
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
    "issues": ["퇴직금", "임금"],
    "articles_by_issue": {
      "퇴직금": [{...조문 데이터...}]
    }
  }
  ```

### 단계 3-2: 체크리스트 및 추가 질의 (Checklist)
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

### 단계 3-3: 최종 결론 도출 (Conclusion)
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
    "conclusion": "근로자퇴직급여 보장법에 따라 퇴직물 지급 대상입니다...",
    "laws": [...],
    "penalty_supplementary": "3년 이하의 징역 또는 3천만원 이하의 벌금...",
    "related_questions": ["지연 이자는 어떻게 되나요?"]
  }
  ```

---

## 4. 단답형 QA (Knowledge & Calculation)

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
- **Request Body:** `지식 QA`와 동일
- **Response:** 계산 방법 및 공식 안내 텍스트

---

## 💡 개발 팁 (프론트엔드 연동)

1. **상태 관리:** 챗봇 UI에서 사용자가 입력한 API 키를 상태(State)나 브라우저 스토리지에 저장해두고, 모든 `POST` 요청의 Body 최상단에 주입(`openai_api_key`: "...")해주시면 됩니다.
2. **스트리밍 결론:** 결론 도출 단계(`step3_conclusion`)는 길어질 수 있습니다. `stream: true` 옵션을 사용해 SSE(`text/event-stream`)로 수신하면 한 글자씩 타이핑되는 효과를 적용할 수 있습니다.
3. **API 명세서:** 더 자세한 파라미터 속성은 `https://law-chat-api.onrender.com/docs` (Swagger UI)에서 확인하고 직접 테스트해 볼 수 있습니다.
