# LawChat 프로젝트 검토: 프로그래밍·기획 관점

전체 코드·기획 검사 후 아쉬운 점을 정리한 문서입니다.

---

## 진입점 역할 (정리)

- **`app.py`**: 개발자·기획자용. 4단계(상황→이슈→체크리스트→결론) 상세 플로우, 장별 둘러보기, 벡터 스토어 재구축 등 **내부 검증·기획용**.
- **`app_chatbot.py`**: **실제 서비스용**. 대화형 채팅 UI, 일반 사용자에게 제공. 배포 시 Main file은 **app_chatbot.py**로 지정.

---

## 1. 프로그래밍적으로 아쉬운 점

### 1.1 로깅·디버깅

- **`print(..., file=sys.stderr)` 다수 사용**  
  `rag/llm.py`, `rag/pipeline.py`, `rag/load_laws.py` 등에서 표준 로깅 대신 stderr 출력 사용.
- **영향**: 로그 레벨 조절 불가, 포맷 통일 어려움, Cloud/배포 환경에서 노이즈.
- **권장**: `logging` 모듈 도입 후 `DEBUG`/`INFO`/`WARNING` 구분, 필요 시 환경변수로 레벨 제어.

### 1.2 디버그 플래그

- **`rag/pipeline.py`**: `DEBUG = True` 하드코딩. 주석에는 "환경변수로 제어 가능"이라 되어 있으나 실제로는 미반영.
- **권장**: `DEBUG = os.getenv("LAW_DEBUG", "0") == "1"` 등으로 환경에서만 켜기.

### 1.3 설정·환경

- **`config.CHAT_MODEL`**: 기본값 `"gpt-5-nano"`. 실제 OpenAI 모델명과 다를 수 있음 (예: `gpt-4o-mini` 등). 잘못된 기본값이면 모든 LLM 호출 실패.
- **권장**: 사용 중인 모델명으로 기본값 맞추거나, README/배포 가이드에 필수 env 명시.

### 1.4 API 캐시와 LAW_API_OC

- **`rag/api_cache.py`**: 캐시 미스 시 `search_list()` 호출. `LAW_API_OC`가 없으면 `law_api_client._ensure_oc()`에서 `ValueError` 발생.
- **영향**: Streamlit Cloud 등에서 Secrets 미설정 시 step3(연관법령/선례) 구간에서 앱 크래시.
- **권장**: `get_aiSearch_cached` / `get_aiRltLs_cached`에서 `ValueError` 등 예외를 잡아 `{"success": False, "data": None}` 또는 빈 결과 반환하고, UI에서는 "연관법령은 API 키 설정 시에만 표시됩니다" 등 안내.

### 1.5 예외 처리

- **광범위한 `except Exception` / `except:`**  
  `pipeline.py`, `app.py`, `store.py`, `api_data_loader.py` 등 여러 곳에서 사용.
- **영향**: 네트워크/키 오류와 논리 오류가 구분되지 않고 삼켜질 수 있음.
- **권장**:  
  - 재발생해야 할 것은 `raise`  
  - 사용자에게 보여줄 메시지만 처리하고 나머지는 최소한 로그 후 재발생  
  - 가능하면 `requests.RequestException`, `openai.APIError` 등 구체적 예외 처리.

### 1.6 LLM 모듈의 프로덕션 부적합 로그

- **`rag/llm.py`**: `[chat] API 응답...`, `choice.__dict__` 등 상세 디버그 출력이 항상 실행됨.
- **권장**: `if DEBUG:` 또는 `logging.getLogger(__name__).debug(...)` 로 감싸서 프로덕션에서는 끄기.

### 1.7 테스트

- **단위 테스트 부재**: `pytest`/`unittest` 기반 테스트 디렉터리·파일이 없음.
- **시나리오 테스트만 존재**: `scripts/test_scenarios.py`, `test_scenario()` 등으로 E2E 성격만 있음.
- **권장**:  
  - `rag/pipeline.py`의 `step1`/`step2`/`step3`, `rag/store` 검색, `rag/llm`의 `extract_json` 등에 단위 테스트 추가  
  - CI에서 `pytest tests/` 실행.

### 1.8 의존성 버전

- **`requirements.txt`**: `openai>=1.40.0`, `streamlit>=1.28.0` 등 하한만 지정. 상한 없음.
- **영향**: 미래 메이저 업데이트에서 breaking change 시 깨질 수 있음.
- **권장**: 중요 라이브러리는 `openai>=1.40.0,<3.0.0` 형태로 상한 두거나, 주기적으로 lock 파일/CI로 호환 검증.

### 1.9 UI 코드 구조 (app.py)

- **`app.py` 850줄 이상**, `main()` 한 함수에 단계별 분기가 모두 포함 (input → issues → issue_select → checklist → conclusion → all_conclusions).
- **영향**: 가독성·수정 시 부담, 단계별 UI만 따로 테스트하기 어려움.
- **권장**:  
  - `render_input_step()`, `render_checklist_step()` 등 단계별 함수로 분리  
  - 또는 `st.session_state.step` 값으로 라우팅하는 작은 디스패처 + 단계별 렌더러.

### 1.10 타입 힌트

- **일부만 사용**: `pipeline.py`, `store.py` 등은 타입 힌트가 있으나, `app.py`, `api_cache.py`, 여러 스크립트는 인자/반환 타입이 없음.
- **권장**: 공개 함수·RAG 파이프라인 인터페이스부터 `str`, `List[Dict[str, Any]]` 등으로 맞추면 유지보수·리팩터 시 도움.

### 1.11 변수명·스코프

- **`rag/store.py`**: `build_vector_store` 내부에서 `for i, c in enumerate(chunks)` 후, 긴 문서 분할 시 `chunks = []` 로 재사용해 상위 `chunks`를 가림.
- **권장**: 내부 루프용 변수명을 `sub_chunks` 등으로 바꿔 의미 구분.

### 1.12 시크릿·환경

- **`.env`**: 로컬만 로드. Cloud는 README에 Secrets 안내 있음.
- **권장**: `OPENAI_API_KEY` 없을 때 앱 초기 화면/사이드바에 "Secrets에 OPENAI_API_KEY를 설정해 주세요" 문구 노출 (이미 벡터 스토어 로드 실패 시 안내는 추가된 상태).

---

## 2. 기획적으로 아쉬운 점

### 2.1 진입점 역할 (적용됨)

- **`app.py`**: 개발·기획용 (4단계 상세 플로우, 벡터 재구축 등).
- **`app_chatbot.py`**: **실제 서비스용** (채팅형). 배포 시 Main file path = **app_chatbot.py**.
- 문서(README, LOCAL_VS_STREAMLIT)에 위 역할 명시됨.

### 2.2 시나리오(추천 키워드) 고정

- **`SCENARIO_QUICK`**: 퇴직금, 해고, 연차·휴가, 임금 체불, 근로시간, 근로계약 6개 고정.
- **영향**: 사용 패턴·인기 이슈가 반영되지 않음.
- **권장**:  
  - (선택) 로그 기반 "자주 묻는 상황" 노출  
  - 또는 설정/문서로 "다른 예시는 이런 문장으로 입력해 보세요" 안내.

### 2.3 에러 메시지 사용자 노출

- **일부 구간**: `str(e)` 그대로 `st.error()`에 표시. 스택 트레이스나 내부 경로가 노출될 수 있음.
- **권장**: 사용자용 메시지는 "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요." 등으로 고정하고, 상세 내용은 로그에만.

### 2.4 법령 데이터 갱신 정책

- **동기화**: `sync_all.py` + (선택) 스케줄러. "법령이 바뀌었을 때 어떻게 알리고, 언제 재동기화·재임베딩할지"에 대한 제품 차원 정책이 문서에만 있고 앱 내 안내는 없음.
- **권장**:  
  - 앱 푸터/사이드바에 "기준 데이터: YYYY-MM-DD 동기화" 표시 (가능하면 `api_data/` 메타데이터에서 읽기)  
  - "최신 법령 반영을 위해 관리자가 동기화를 실행해야 합니다" 정도의 짧은 설명.

### 2.5 접근성·다국어

- **UI 텍스트**: 한글 고정. 시각/키보드 접근성(ARIA, 포커스 등)에 대한 정책 없음.
- **권장**:  
  - 단기: 최소한 버튼/라벨에 일관된 한글 사용, 오류 문구 명확화  
  - 중장기: 다국어/접근성 요구가 있으면 i18n·접근성 가이드 적용 검토.

### 2.6 첫 사용자 가이드

- **현재**: 상황 입력란 + 시나리오 버튼만 있음. "무엇을 입력하면 되는지", "체크리스트에서 모르겠음이 있으면 어떻게 되는지" 등이 앱 안에 없음.
- **권장**:  
  - 접이식 "사용 방법" 또는 "예시" 섹션  
  - 체크리스트 단계에 "모르겠음도 선택 가능하며, 가능한 범위에서 결론을 드립니다" 등 한 줄 안내.

### 2.7 세션·상태

- **Streamlit**: 새로고침 시 세션 초기화. 장시간 상담 중 새로고침하면 처음부터 다시 진행.
- **권장**:  
  - "결론까지 진행 중이었다면 새로고침하지 마세요" 같은 짧은 안내  
  - (선택) 결론 텍스트를 로컬 다운로드/복사 버튼으로 남기기.

### 2.8 부하·비용

- **LLM/임베딩**: 요청마다 API 호출. 동시 접속이 많으면 비용·지연 증가.
- **권장**:  
  - 동시 사용자 수가 많아지면 캐싱(동일 상황+이슈+체크리스트 답변 → 동일 결론 재사용) 검토  
  - 비용 한도/알림 정책을 README 또는 운영 문서에 명시.

### 2.9 문서 정리

- **docs/**: `LOCAL_VS_STREAMLIT.md`, `API_STORAGE_STRATEGY.md` 등 유용한 문서가 있으나, `TODO_verify_law_terms.md`, `cleaned_test_files.md` 등 과거 작업 이력성 문서가 섞여 있음.
- **README**: "vector_store/는 .gitignore"라고 되어 있으나, Streamlit Cloud 배포를 위해 vector_store를 커밋하는 방식으로 변경된 상태와 불일치 가능성.
- **권장**:  
  - "현재 배포 방식(로컬 vs Cloud, vector_store 커밋 여부)"를 한 곳에 정리  
  - 검증 완료된 항목은 별도 체크리스트로 두고, 이력성 문서는 `docs/archive/` 등으로 이동 검토.

---

## 3. 요약 체크리스트

| 구분 | 항목 | 우선순위 |
|------|------|----------|
| 코드 | logging 모듈로 전환, DEBUG 환경변수화 | 중 |
| 코드 | api_cache에서 LAW_API_OC 없을 때 예외 처리 | 높음 |
| 코드 | llm.py 디버그 출력 조건부 처리 | 중 |
| 코드 | app.py 단계별 함수 분리 | 중 |
| 코드 | 단위 테스트 추가 (pipeline, store, llm) | 중 |
| 코드 | requirements 상한 또는 CI 검증 | 낮음 |
| 기획 | app.py vs app_chatbot.py 정리(통합 또는 역할 명시) | 높음 |
| 기획 | 사용자용 에러 메시지 정리, 첫 사용 가이드 | 중 |
| 기획 | 데이터 기준일/동기화 안내 노출 | 낮음 |
| 문서 | README·docs와 현재 배포 방식 일치시키기 | 중 |

---

## 적용 이력 (챗봇 = 실제 서비스 기준)

- **진입점 역할**: app.py = 개발/기획용, app_chatbot.py = 서비스용 → REVIEW, LOCAL_VS_STREAMLIT, README 반영.
- **api_cache**: LAW_API_OC 없거나 API 실패 시 `{"success": False, "data": None}` 반환하도록 예외 처리.
- **app_chatbot.py**: 사용자용 고정 에러 메시지(`USER_FACING_ERROR`), 그래프 로드 실패 시에도 사이드바·입력 UI 유지, `get_chapters()` 예외 처리.
- **DEBUG**: pipeline `DEBUG`, llm `_DEBUG`를 환경변수 `LAW_DEBUG=1` 일 때만 출력하도록 변경.
- **README**: 서비스 배포 시 Main file path = `app_chatbot.py` 로 안내 추가.

이 문서는 한 번에 반영할 체크리스트라기보다, 단계적으로 개선할 때 참고용으로 사용하시면 됩니다.
