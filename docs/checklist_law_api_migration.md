# 법령 API 도입 시 체크리스트

법령 원문을 **현행법령 API**에서 가져오도록 전환할 때, 확인·수정해야 할 위치와 작업을 정리한 문서입니다.

---

## 1. 설정·환경

| 구분 | 위치 | 체크 내용 |
|------|------|-----------|
| **API 키·URL** | `config.py` 또는 `.env` | `LAW_API_KEY`, `LAW_API_BASE_URL` 등 API 인증·엔드포인트 추가. 공개 API면 키 발급 절차 확인. |
| **LAWS_DIR** | `config.py` | API 동기화 시에도 “캐시 저장 경로”로 쓸지, 또는 `LAWS_CACHE_DIR` 별도 두고 기존 `LAWS_DIR`는 MD 수동용으로 유지할지 결정. |
| **SOURCE_LAW** | `config.py` | API에서 가져온 법률의 `source` 값. 기존 `"근로기준법(법률)"` 유지하면 검색 필터 호환. |
| **레이트 리밋** | API 문서 | 목록/본문 호출 제한. 배치 동기화 시 sleep·캐시 전략 수립. |

---

## 2. 데이터 로드 경로 (핵심)

| 구분 | 위치 | 체크 내용 |
|------|------|-----------|
| **진입점** | `rag/store.py` | `build_vector_store()` → `chunks = load_laws_from_dir(LAWS_DIR)`. 여기를 “API에서 청크 목록 가져오기”로 바꾸거나, **새 함수** `load_laws_from_api()` 를 만들어 청크 리스트 반환 후 `load_laws_from_dir` 대신 사용. |
| **로더** | `rag/load_laws.py` | 현재 `load_laws_from_dir()`는 `laws_dir.glob("*.md")`로 MD만 읽음. API 도입 시: (1) **API 전용 로더** `load_laws_from_api()` 신설해 API 응답 → 청크 리스트 변환, (2) 또는 API 동기화 스크립트가 **MD/JSON을 갱신**하고 기존 `load_laws_from_dir()` 은 그대로 두는 방식. |
| **청크 형식** | `rag/load_laws.py`, `rag/store.py` | store가 기대하는 청크 키: `source`, `article`, `text`, `embedding_text`, `kind`, `section`, `chapter`, (선택) `primary_category`. API 응답을 이 형식으로 변환하는 로직 필요. |
| **조 단위 파싱** | `rag/load_laws.py` | 현재는 MD의 `#### [법률] 제34조(퇴직금)` 패턴으로 조 분리. API가 “조 단위”를 주지 않으면 **API 본문 → 조 단위 파싱** 규칙을 새로 작성 (예: 정규식 또는 API가 주는 조 목록 활용). |

---

## 3. 분류·메타데이터(JSON) 연동

| 구분 | 위치 | 체크 내용 |
|------|------|-----------|
| **분류 JSON** | `rag/law_json.py` | `JSON_PATH = LAWS_DIR / "근로기준법_분류.json"`. API 본문만 쓸 경우 **조문 번호(제34조 등) 기준으로 JSON과 매칭**해 enrichment 적용. API에 조 번호가 있으면 그걸로 `get_article_info(art)` 호출. |
| **Enrichment** | `rag/load_laws.py`, `rag/law_json.py` | `get_chunk_enrichment(c, label)`는 `c["article"]`(예: `제34조(퇴직금)`)로 JSON 조회. API에서 오는 청크도 `article` 필드를 동일 규칙으로 두면 기존 enrichment 그대로 사용 가능. |
| **이슈·관련어** | `rag/law_json.py` | 이슈별 조문 추론은 전부 **JSON(근로기준법_분류.json)** 기반. API 전환해도 이 JSON은 유지해야 함. (API는 “원문”, JSON은 “분류·키워드·이슈 매핑”) |

---

## 4. 벡터 스토어

| 구분 | 위치 | 체크 내용 |
|------|------|-----------|
| **구축** | `rag/store.py` | `chunks`에 `source`, `article`, `section`, `chapter`, `primary_category` 등 메타 유지. API 청크가 동일 키를 가지면 수정 최소화. |
| **재구축** | `rag/store.py` | API 주기 동기화 시 `build_vector_store(force_rebuild=True)` 호출해 전체 재임베딩할지, “변경분만 추가”할지 정책 결정. |
| **검색 필터** | `rag/store.py`, `rag/graph.py`, `rag/pipeline.py`, `app.py` | `filter_sources=[SOURCE_LAW]`, `exclude_sections`, `exclude_chapters` 등. API에서 오는 청크의 `source`/`section`/`chapter` 값이 기존과 동일해야 함. |

---

## 5. API 사용하는 쪽(신규·수정)

| 구분 | 위치 | 체크 내용 |
|------|------|-----------|
| **API 클라이언트** | 신규 `rag/law_api.py` (가정) | 현행법령 API “목록 JSON”·“본문 JSON” 호출, 에러·재시도·타임아웃 처리. |
| **동기화 스크립트** | 신규 `scripts/sync_laws_from_api.py` (가정) | 목록 조회 → 근로기준법 선택 → 본문 조회 → 조 단위 파싱 → `laws/` 에 MD 저장 또는 청크 리스트를 직접 벡터 스토어에 넣기. |
| **청크 변환** | `rag/law_api.py` 또는 `rag/load_laws.py` | API 응답 → `{ "source", "article", "text", "embedding_text", "kind", "section", "chapter" }` 형태. 본문에 장/절 정보가 있으면 파싱해 `chapter`, `section` 채우기. |

---

## 6. 앱·그래프·파이프라인

| 구분 | 위치 | 체크 내용 |
|------|------|-----------|
| **검색 소스** | `app.py`, `rag/graph.py`, `rag/pipeline.py` | `SOURCE_LAW`, `SOURCE_DECREE`, `SOURCE_RULE` 사용처. API에서 가져온 법률도 `source` 값을 동일하게 두면 **코드 수정 없이** 필터 유지. |
| **캡션·안내 문구** | `app.py`, `app_chatbot.py`, `main.py` | “근로기준법 등 노동법령 데이터 기반” 등. API 사용 시 “법제처 현행법령 API 기반” 등으로 문구만 바꿀지 결정. |
| **프롬프트** | `rag/prompts.py` | “근로기준법 등 노동법령 데이터만 인용” 등. API 전환만으로는 수정 불필요. |

---

## 7. 스크립트·테스트

| 구분 | 위치 | 체크 내용 |
|------|------|-----------|
| **검증 스크립트** | `scripts/check_retirement_articles.py` | `SOURCE_LAW`로 검색. API 기반 청크도 `source=SOURCE_LAW` 이면 그대로 동작. |
| **품질 검사** | `scripts/check_law_json_quality.py` | `laws/근로기준법_분류.json` 경로. JSON은 계속 로컬 관리이므로 경로만 확인. |
| **기타 스크립트** | `scripts/extract_issues_from_json.py`, `sort_law_json.py`, `add_chapter_hierarchy.py` 등 | 모두 `laws/` 또는 `근로기준법_분류.json` 기준. API는 “원문”만 대체하므로, **분류 JSON을 수동/반자동 유지**하면 스크립트는 그대로 사용 가능. |

---

## 8. 운영·배포

| 구분 | 체크 내용 |
|------|-----------|
| **동기화 주기** | API → 로컬/벡터 갱신을 언제 할지 (cron, 수동, CI). |
| **실패 시** | API 장애 시 “기존 벡터 스토어 그대로 사용”할지, 에러 페이지/메시지 노출할지. |
| **버전 표시** | “기준 법령: 20XX년 X월 X일 현재” 등 표시할지. API 응답에 시행일이 있으면 활용. |

---

## 9. 한 줄 요약

- **반드시 손댐**: `config.py`(API 설정), **데이터 진입점** (`store.py`의 `load_laws_from_dir` 호출부 또는 새 `load_laws_from_api`), **API 응답 → 청크 형식** 변환, **조 단위 파싱** (API가 조 단위를 안 주는 경우).
- **유지하면 됨**: `SOURCE_LAW` 등 기존 상수, `filter_sources=[SOURCE_LAW]` 사용처, **분류 JSON**(`law_json.py`, `근로기준법_분류.json`) 및 이슈/관련어/필터 로직, `get_chunk_enrichment` (청크에 `article`만 맞추면 됨).
- **선택**: `LAWS_DIR`를 API 캐시 전용으로 둘지, 동기화 스크립트로 MD를 갱신해 기존 `load_laws_from_dir`만 쓰는 방식으로 갈지.

이 체크리스트대로 진행하면 “법령 자체를 API로 붙인다” 전환 시 빠뜨릴 부분을 줄일 수 있습니다.
