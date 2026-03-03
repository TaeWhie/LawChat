# -*- coding: utf-8 -*-
"""
상황·체크리스트 반영 판례 검색을 **직접 확인**하기 위한 스크립트.

API 연속 호출 시 봇으로 인지될 수 있으므로:
- 기본(dry run): API 호출 없이 쿼리만 생성·캐시 폴백만 실행해 확인
- --one-call: API 호출을 **1회만** 시도 (호출 전 5초 대기)

사용법:
  python scripts/verify_precedents_situation_search.py
      → API 호출 없이 쿼리 생성 + 캐시 폴백만 확인

  python scripts/verify_precedents_situation_search.py --one-call
      → 5초 대기 후 상황 반영 검색 1회 시도 (API 성공 시 source=api 확인)
      ※ 연속 실행하지 말 것. 필요할 때 한 번만 실행해 확인용으로 사용.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(
        description="상황·체크리스트 반영 판례 검증 (API 호출 최소화)"
    )
    parser.add_argument(
        "--one-call",
        action="store_true",
        help="API 호출 1회만 시도 (호출 전 5초 대기). 연속 실행 금지.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="--one-call 사용 시 호출 전 대기 시간(초). 기본 5초.",
    )
    args = parser.parse_args()

    from rag.api_data_loader import (
        _build_precedent_search_query,
        get_precedents_for_conclusion,
        get_precedents_from_cache_with_meta,
    )

    # 샘플: 정리해고 상황 + 체크리스트 답변
    issue = "해고/징계"
    situation = "3년 동안 제조업 다녔는데 회사가 정리해고 하겠다고 해요."
    qa_text = """Q: 정리해고 사유를 회사에서 무엇이라고 했나요?
A: 경영 악화
Q: 해고예고를 받았나요?
A: 네 50일 전에 받았어요"""

    print("=" * 70)
    print("상황·체크리스트 반영 판례 검증")
    print("=" * 70)
    print(f"이슈: {issue}")
    print(f"상황: {situation}")
    print(f"체크리스트 예시:\n{qa_text}")
    print()

    # 1) 쿼리 생성만 (API 호출 없음)
    query = _build_precedent_search_query(issue, situation=situation, qa_text=qa_text)
    print("[1] 검색 쿼리 (이 쿼리로 API 검색 시도 또는 캐시 키로 사용)")
    print(f"    {query!r}")
    print()

    # 2) 캐시만 사용한 경우 (API 호출 없이) — 항상 실행
    print("[2] 캐시 폴백만 사용 시 (API 호출 없이 확인)")
    precs_cache, meta_cache = get_precedents_from_cache_with_meta(issue, max_results=3)
    print(f"    source: cache (고정)")
    print(f"    keyword_used: {meta_cache.get('keyword_used')!r}")
    print(f"    로딩 건수: {len(precs_cache)}건")
    if meta_cache.get("titles"):
        for i, t in enumerate(meta_cache["titles"][:3], 1):
            print(f"      {i}. {t[:55]}{'…' if len(t) > 55 else ''}")
    print()

    if not args.one_call:
        print("[3] 상황 반영 API 검색은 실행하지 않음 (API 호출 0회)")
        print("    → API 경로 확인 시: python scripts/verify_precedents_situation_search.py --one-call")
        print("    → 연속 실행하지 말고, 필요할 때 1번만 실행할 것 (봇 차단 주의)")
        print("=" * 70)
        return

    # 3) API 1회만 시도 (대기 후)
    print(f"[3] API 호출 1회 시도 (호출 전 {args.delay}초 대기 중…)")
    print("    ※ 연속 실행하지 마세요. 봇으로 인지될 수 있습니다.")
    time.sleep(args.delay)
    precs, meta = get_precedents_for_conclusion(
        issue, situation=situation, qa_text=qa_text, max_results=3
    )
    print()
    print("    결과:")
    print(f"    source: {meta.get('source')}")
    print(f"    query_used: {meta.get('query_used')!r}")
    print(f"    로딩 건수: {meta.get('count')}건")
    if meta.get("titles"):
        for i, t in enumerate(meta["titles"][:5], 1):
            print(f"      {i}. {t[:55]}{'…' if len(t) > 55 else ''}")
    if meta.get("error"):
        print(f"    (API 오류 시 캐시 사용됨: {meta.get('error')})")
    print()
    print("=" * 70)
    if meta.get("source") == "api":
        print("✓ 상황 반영 API 검색이 사용되었습니다 (query_used에 검색어 확인).")
    else:
        print("이번에는 캐시가 사용되었습니다. 네트워크/API 상태가 좋을 때 다시 --one-call 실행해 보세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()
