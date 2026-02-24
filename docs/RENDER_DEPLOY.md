# Render API 서버 배포 가이드

## 요약

- **API 서버**: `main_api.py` (FastAPI + uvicorn)
- **챗봇과 동일한 1회 호출**: `POST /api/v1/chat/invoke` (graph.invoke와 동일)
- **배포 설정**: 루트의 `render.yaml`, `Dockerfile` 사용

## 배포 전 확인 사항

### 1. 데이터 디렉터리 (필수)

Render는 **에피소드 디스크**를 사용하므로, 다음 디렉터리가 **저장소에 포함**되어 있어야 합니다.

| 디렉터리 | 용도 | 없을 때 |
|----------|------|---------|
| `vector_store/` | RAG 벡터 검색 | `build_vector_store()` 실패 → 서버 기동 실패 |
| `api_data/` (laws, terms, precedents 등) | 법령·판례·용어 데이터 | 법률 목록/장/조문 API 빈 결과 또는 오류 |

- `.gitignore`에서 `vector_store/`가 **주석 처리**되어 있으면 커밋 가능. (Streamlit Cloud 배포 시 커밋하여 사용한다는 주석 참고)
- `api_data/cache/`만 gitignore 되어 있으면, `api_data/laws/`, `api_data/terms/`, `api_data/precedents/` 등은 커밋 필요.

### 2. 환경 변수 (Render 대시보드)

| 키 | 설명 | 필수 |
|----|------|------|
| `OPENAI_API_KEY` | OpenAI(또는 호환) API 키 | ✅ |
| `LAW_API_OC` | 국가법령정보 API OC 키 (서류·법령 검색 등) | 서류/법령 API 사용 시 |
| `ALLOWED_ORIGINS` | CORS 허용 오리진 (쉼표 구분, 기본 `*`) | 선택 |
| `LAW_API_VERSION` | 헬스·앱 버전 표시 (기본 `1.2.0`) | 선택 |
| `LAW_DEBUG` | `1`이면 오류 상세·DEBUG 로그 노출 (운영 시 비권장) | 선택 |

`render.yaml`에서 `OPENAI_API_KEY`, `LAW_API_OC`는 `sync: false`로 두었으므로 **Render 대시보드에서 값을 입력**해야 합니다.

### 3. 기동 시간·헬스체크

- `build_vector_store()`가 기동 시 한 번 실행되며, `vector_store/` 크기에 따라 수십 초 걸릴 수 있습니다.
- Render 무료 플랜은 기동 타임아웃이 짧을 수 있으므로, **vector_store를 미리 구축해 커밋**하는 것을 권장합니다.
- `render.yaml`에 `healthCheckPath: /api/v1/health`가 설정되어 있어, 기동 후 해당 엔드포인트가 2xx를 반환할 때까지 Render가 트래픽을 보내지 않습니다. 기동이 오래 걸리면 Render 대시보드에서 헬스체크 타임아웃을 넉넉히 두거나, 벡터 스토어를 미리 커밋해 두세요.

## 챗봇과 동일한 동작 (API)

**app_chatbot**은 `graph.invoke({"messages": [HumanMessage(...)]})` 한 번으로 전체 플로우(라우팅 → 이슈분류 → 체크리스트/결론, 지식·계산·서류 분기)를 수행합니다.

API에서 **동일한 1회 호출**로 같은 결과를 얻으려면:

- **엔드포인트**: `POST /api/v1/chat/invoke`
- **Body (JSON)**  
  - `message`: 사용자 입력 문자열  
  - `thread_id`: (선택) 대화 스레드 ID, 기본 `"default"`  
  - `openai_api_key`: (선택) 요청 단위 API 키. 법령 API 키는 서버 Secret(`LAW_API_OC`)만 사용

**요청 Body (JSON)** 에서 선택적으로 다음을 넣을 수 있습니다.

- `message`: 사용자 입력 (필수)
- `thread_id`: 대화 스레드 ID (기본 `"default"`)
- `openai_api_key`: 요청 단위 OpenAI API 키 (미설정 시 서버 환경변수 사용)
- `openai_base_url`: OpenAI 호출 Base URL (Azure·프록시 등, 미설정 시 서버 기본값)
- `model`: 채팅 모델 오버라이드 (예: `gpt-4o`, `gpt-4o-mini`, 미설정 시 서버 `LAW_CHAT_MODEL` 사용)

법령 API(국가법령정보 OC) 키는 **요청으로 받지 않으며**, 서버 Secret `LAW_API_OC`만 사용합니다.

**응답**은 app_chatbot의 `_serialize_ok_result`와 동일한 구조입니다.

- `status`: `"ok"`
- `messages`: `[{ "t": "HumanMessage"|"AIMessage", "c": "내용" }, ...]`
- `phase`: `"input"` | `"checklist"` | `"conclusion"`
- `checklist`, `selected_issue`, `situation`, `articles_by_issue`, `checklist_rag_results`

프론트엔드에서 이 한 엔드포인트만 호출하면 **chatbot.py와 같은 성능(동일 그래프)**을 낼 수 있습니다.

## 기타 API 엔드포인트

- 단계별: `POST /api/v1/chat/classify`, `POST /api/v1/chat/checklist`, `POST /api/v1/chat/conclusion`
- 라우팅: `POST /api/v1/chat/route`
- QA: `POST /api/v1/chat/qa/knowledge`, `calculation`, `documents`
- 법률 둘러보기: `GET /api/v1/laws/list`, `GET /api/v1/laws/chapters`, `GET /api/v1/laws/articles/{chapter_number}`
- 헬스: `GET /api/v1/health`

## 문제 해결

- **기동 실패**: `vector_store/` 또는 `api_data/` 없음 → 위 데이터 디렉터리 확인.
- **500 / 상담 처리 중 오류**: `OPENAI_API_KEY` 미설정 또는 만료, 네트워크 차단 등 확인.
- **법률 목록/장/조문 빈 결과**: `api_data/laws/` 등 동기화 데이터가 저장소에 포함되어 있는지 확인.
