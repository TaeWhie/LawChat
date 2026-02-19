# 정리된 테스트 파일 목록

**정리 일시**: 2026-02-13

## 삭제된 테스트 스크립트 (9개)

1. `scripts/test_api.py` - 초기 테스트 스크립트
2. `scripts/test_failed_apis.py` - 실패한 API 재테스트
3. `scripts/test_committees_comparison.py` - 위원회 비교 테스트
4. `scripts/test_xml_format.py` - XML 형식 테스트
5. `scripts/test_with_headers.py` - 헤더 테스트 (test_all_apis에 통합됨)
6. `scripts/test_timeout_apis.py` - 타임아웃 API 테스트
7. `scripts/test_lstrmRltJo_final.py` - 법령용어-조문 연계 최종 확인
8. `scripts/debug_failed_apis.py` - 디버깅 스크립트
9. `scripts/exact_comparison.py` - 정확한 비교 테스트

## 삭제된 테스트 문서 (6개)

1. `docs/api_test_results.md` - 초기 테스트 결과
2. `docs/api_comprehensive_test_report.md` - 중간 보고서
3. `docs/api_final_test_results.md` - 중간 최종 결과
4. `docs/api_debugging_results.md` - 디버깅 결과
5. `docs/api_final_solution.md` - 중간 해결책
6. `docs/api_solution_found.md` - 해결 발견 문서

## 유지된 파일

### 테스트 스크립트
- `scripts/test_all_apis.py` - 최종 통합 테스트 스크립트 (브라우저 헤더 포함)

### 문서
- `docs/API_TEST_FINAL.md` - 최종 테스트 결과 문서
- `docs/law_api_spec.md` - API 스펙 문서
- `docs/API_checked_items.md` - 체크 항목 목록
- `docs/FINAL_VERIFICATION.md` - 최종 검증 보고서
- `docs/verification_checklist.md` - 검증 체크리스트

## 정리 이유

- 중복된 테스트 스크립트와 문서 정리
- 최종 검증 완료 후 임시 파일 삭제
- 프로젝트 구조 단순화
