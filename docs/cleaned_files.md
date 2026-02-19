# 정리된 파일 목록

## 삭제된 파일들 (총 39개)

### 첫 번째 정리 (23개)

### API 크롤링 관련 스크립트 (14개)
- `scripts/extract_all_htmlnames.py` - API 가이드 크롤링 (작업 완료)
- `scripts/save_and_analyze_html.py` - HTML 분석용 임시 스크립트
- `scripts/extract_table_links.py` - 테이블 링크 추출
- `scripts/analyze_html_structure.py` - HTML 구조 분석
- `scripts/crawl_all_guides.py` - 가이드 크롤링
- `scripts/systematic_guide_fetch.py` - 체계적 가이드 가져오기
- `scripts/parse_guide_list_comprehensive.py` - 가이드 목록 파싱
- `scripts/try_all_patterns.py` - 패턴 시도
- `scripts/find_guide_links_detailed.py` - 상세 링크 찾기
- `scripts/extract_and_fetch_guides.py` - 가이드 추출 및 가져오기
- `scripts/find_all_guide_links.py` - 모든 링크 찾기
- `scripts/systematic_fetch_guides.py` - 체계적 가이드 가져오기
- `scripts/parse_guide_list.py` - 가이드 목록 파싱
- `scripts/fetch_api_guides.py` - API 가이드 가져오기

### 임시 HTML/JSON 파일 (9개)
- `guide_list_page.html` - 임시 HTML 파일
- `api_guide_results.json` - 크롤링 결과 (작업 완료)
- `extracted_guide_links.json` - 추출된 링크
- `systematic_guide_results.json` - 체계적 결과
- `parsed_guide_links.json` - 파싱된 링크
- `pattern_based_results.json` - 패턴 기반 결과
- `checked_items_guides.json` - 체크 항목 가이드
- `guide_matches.json` - 가이드 매칭 결과

### 테스트/시뮬레이션 파일 (2개)
- `simulate_streamlit.py` - Streamlit 시뮬레이션
- `simulate_narrow.py` - 좁히기 시뮬레이션

## 유지된 파일들

### 메인 애플리케이션
- `main.py` - CLI 메인
- `app.py` - Streamlit 메인 UI
- `app_chatbot.py` - LangGraph 챗봇 UI
- `config.py` - 설정 파일

### RAG 모듈
- `rag/__init__.py`
- `rag/llm.py`
- `rag/pipeline.py`
- `rag/store.py`
- `rag/prompts.py`
- `rag/load_laws.py`
- `rag/law_json.py`
- `rag/precedent_query.py`
- `rag/graph.py`

### 유틸리티 스크립트 (유지)
- `scripts/check_retirement_articles.py` - 퇴직금 조항 검증
- `scripts/extract_issues_from_json.py` - 이슈 추출
- `scripts/check_law_json_quality.py` - JSON 품질 검사
- `scripts/sort_law_json.py` - JSON 정렬
- `scripts/add_chapter_hierarchy.py` - 장 계층 추가
- `scripts/add_related_articles.py` - 관련 조문 추가
- `scripts/symmetrize_related_articles.py` - 관련 조문 대칭화
- `scripts/trace_issue_flow.py` - 이슈 흐름 추적 (디버깅용)

### 문서
- `docs/law_api_spec.md` - API 스펙 문서
- `docs/API_checked_items.md` - 체크 항목 목록
- `docs/FINAL_VERIFICATION.md` - 최종 검증 보고서
- `docs/verification_checklist.md` - 검증 체크리스트

### 기타
- `requirements.txt` - 의존성 목록
- `run_chatbot.bat` - 챗봇 실행 배치 파일
- `run_local.bat` - 로컬 실행 배치 파일

---

### 두 번째 정리 (16개) - API 테스트 파일

#### 테스트 스크립트 (9개)
- `scripts/test_api.py` - 초기 테스트
- `scripts/test_failed_apis.py` - 실패한 API 재테스트
- `scripts/test_committees_comparison.py` - 위원회 비교
- `scripts/test_xml_format.py` - XML 형식 테스트
- `scripts/test_with_headers.py` - 헤더 테스트
- `scripts/test_timeout_apis.py` - 타임아웃 테스트
- `scripts/test_lstrmRltJo_final.py` - 최종 확인용
- `scripts/debug_failed_apis.py` - 디버깅용
- `scripts/exact_comparison.py` - 정확한 비교

#### 테스트 문서 (6개)
- `docs/api_test_results.md` - 초기 테스트 결과
- `docs/api_comprehensive_test_report.md` - 중간 보고서
- `docs/api_final_test_results.md` - 중간 최종 결과
- `docs/api_debugging_results.md` - 디버깅 결과
- `docs/api_final_solution.md` - 중간 해결책
- `docs/api_solution_found.md` - 해결 발견 문서

#### 임시 파일 (1개)
- `api_test_all_results.json` - 테스트 결과 JSON
