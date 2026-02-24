# API 서버(main_api.py) 점검 요약

기획·프로그래밍 관점에서의 문제점과 조치 사항을 정리한 문서입니다.

---

## 1. 기획·제품 관점

### 1.1 엔드포인트 역할 중복
- **현상**: 상담 플로우가 두 가지 방식으로 제공됨.
  - **1회 호출**: `POST /api/v1/chat/invoke` (챗봇과 동일, 권장)
  - **단계별**: `classify` → `checklist` → `conclusion` (3회 호출, 상태는 클라이언트 관리)
- **권장**: 프론트엔드는 **invoke 한 종류만** 사용하는 것을 권장. 단계별 API는 디버깅·커스텀 UI용으로만 사용.

### 1.2 API 스펙 문서 부족
- **현상**: `docs/API_USAGE.md`에 `invoke`, `model`, `openai_base_url` 등이 반영되지 않음.
- **권장**: OpenAPI(Swagger)는 FastAPI 기본 제공(`/docs`). API_USAGE.md를 invoke·공통 파라미터 기준으로 최신화.

### 1.3 버전·헬스 정보
- **현상**: `/api/v1/health`의 `version`이 하드코딩(`"1.1.0-absolute-keys-v5"`).
- **권장**: `config` 또는 패키지 버전에서 읽어오거나, 배포 시 환경변수로 주입.

### 1.4 인증·속도 제한 없음
- **현상**: API 키를 요청 body로 받을 뿐, 서비스 수준 인증(API Key 헤더·JWT)이나 Rate Limit 없음.
- **권장**: Render 단일 배포면 서버 env만 써도 되므로 필수는 아님. 다중 클라이언트·상업 운영 시 인증·Rate Limit 도입 검토.

---

## 2. 프로그래밍 관점 (해결된 항목)

### 2.1 ✅ 결론 스트리밍 시 API 키 미전달 (수정 완료)
- **원인**: `stream=true`일 때 `step3_conclusion_stream`을 제너레이터 안에서 호출. 제너레이터는 응답 전송용 스레드에서 실행되어 **ContextVar가 복사되지 않음**.
- **조치**: 스트리밍 사용 시 `effective_key = request.openai_api_key or openai_api_key_ctx.get()`를 핸들러에서 먼저 계산한 뒤, `step3_conclusion_stream(..., openai_api_key=effective_key)`로 전달하도록 수정함.

### 2.2 ✅ documents_qa 예외 미처리 (수정 완료)
- **원인**: `documents_qa`에 try/except가 없어, `search_documents_for_topic` 등에서 예외 시 500 스택 트레이스가 그대로 노출될 수 있음.
- **조치**: try/except 추가 후, 클라이언트에는 "서류·서식 조회 중 오류가 발생했습니다."만 반환하도록 수정함.

### 2.3 ✅ 법률 둘러보기 엔드포인트 예외 처리 (수정 완료)
- **조치**: `list_laws`, `list_chapters`, `list_articles`에 try/except를 넣고, 실패 시 클라이언트에는 안내 메시지만 담은 HTTPException으로 응답하도록 수정함.

---

## 3. 프로그래밍 관점 (추가 개선 — 반영 완료)

### 3.1 ✅ 에러 메시지에 내부 정보 포함
- **조치**: `LAW_DEBUG=1`일 때만 `detail`에 `str(e)` 포함. 기본은 고정 문구만 반환. (`_LAW_DEBUG` 사용)

### 3.2 ✅ classify_issue 디버그 로그
- **조치**: `LAW_DEBUG=1`일 때만 DEBUG 로그 출력.

### 3.3 ✅ classify_issue 오류 시 detail에 키 정보
- **조치**: 클라이언트에는 "이슈 분류 중 오류가 발생했습니다."만 전달. 키/컨텍스트 정보 제거.

### 3.4 ✅ 미사용 import
- **조치**: `re`, `json`, `contextvars`, `jsonable_encoder`, `Body`, `Depends`, `Header`, `Generator` 제거.

### 3.5 ✅ route_question 동기 호출
- **조치**: `classify_type`을 `asyncio.to_thread(classify_type, request.text)`로 실행.

---

## 4. 배포·운영 관점

### 4.1 기동 시 벡터 스토어/데이터
- **필수**: Render 등에서 `vector_store/`, `api_data/`(laws, terms 등)가 포함되거나 마운트되어 있어야 함. 없으면 기동 실패.
- **참고**: `docs/RENDER_DEPLOY.md`에 정리됨.

### 4.2 기동 시간
- **현상**: `build_vector_store()`가 기동 시 한 번 실행되며, 데이터 양에 따라 수십 초 걸릴 수 있음.
- **권장**: Render 무료 플랜 등 타임아웃이 짧으면, 벡터 스토어를 미리 구축해 저장소에 포함하거나, 헬스체크 타임아웃을 넉넉히 설정.

---

## 5. 수정 이력 요약

| 항목 | 조치 |
|------|------|
| 결론 스트리밍 API 키 | 핸들러에서 유효 키 계산 후 `step3_conclusion_stream`에 인자로 전달 |
| documents_qa | try/except 추가, 클라이언트에는 안내 메시지만 반환 |
| list_laws / list_chapters / list_articles | try/except 추가, 실패 시 HTTPException으로 안내 메시지 반환 |
| 에러 메시지 | `LAW_DEBUG=1`일 때만 `detail`에 `str(e)` 포함 |
| classify DEBUG/키 노출 | DEBUG 로그·키 정보 제거, LAW_DEBUG 시에만 로그 |
| 미사용 import | re, json, contextvars, jsonable_encoder, Body, Depends, Header, Generator 제거 |
| route_question | `asyncio.to_thread(classify_type, request.text)` 적용 |
| health 버전 | `LAW_API_VERSION` 환경변수 사용 (기본 "1.2.0") |
