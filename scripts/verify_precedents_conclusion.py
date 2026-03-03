# -*- coding: utf-8 -*-
"""
결론 단계에서 사용하는 판례 데이터가 올바르게 불러와지는지 검증하는 스크립트.

- 각 이슈(primary)에 대해 어떤 키워드로 어떤 캐시 파일을 사용하는지
- 해당 파일에서 몇 건의 판례를 가져오는지, 사건명(제목)은 무엇인지
를 출력해, '있는/없는'이 아니라 '올바른 판례 데이터를 쓰는지' 확인할 수 있습니다.

사용법:
  python scripts/verify_precedents_conclusion.py
  python scripts/verify_precedents_conclusion.py --issue "퇴직금"
  python scripts/verify_precedents_conclusion.py --issue "해고/징계" --max 5
  python scripts/verify_precedents_conclusion.py --demo              # 결론에 실제 들어가는 [판례] 텍스트 + precedents_used 출력
  python scripts/verify_precedents_conclusion.py --out result.txt    # 결과를 UTF-8 파일로 저장 (한글 깨짐 방지)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.api_data_loader import get_precedents_from_cache_with_meta
from rag.labor_keywords import PRIMARY_ISSUES


def run_demo():
    """결론 단계와 동일하게 판례를 불러와, LLM에 전달되는 [판례] 텍스트와 precedents_used를 출력."""
    from rag.pipeline import _add_precedents_and_explanations
    issue = "퇴직금"
    ctx, precedents_used = _add_precedents_and_explanations(issue, "Q: 퇴직금? A: 1년 근무", law_results=[])
    print("=" * 70)
    print("[데모] 결론 단계에서 실제로 LLM에 전달되는 [판례] 컨텍스트")
    print("=" * 70)
    print(ctx[:1200] if ctx else "(없음)")
    print()
    print("=" * 70)
    print("[데모] precedents_used (검증용 메타)")
    print("=" * 70)
    print("사용 키워드:", precedents_used.get("keyword_used"))
    print("캐시 파일:", precedents_used.get("path_used"))
    print("로딩 건수:", precedents_used.get("count"), "건")
    print("사건명:", precedents_used.get("titles"))
    print("판례일련번호:", precedents_used.get("precedent_ids"))
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="결론 단계 판례 로딩 검증")
    parser.add_argument("--issue", type=str, help="단일 이슈만 검증 (미지정 시 PRIMARY_ISSUES 전체)")
    parser.add_argument("--max", type=int, default=5, help="키워드당 최대 판례 건수 (기본 5)")
    parser.add_argument("--demo", action="store_true", help="결론에 들어가는 [판례] 텍스트와 precedents_used 한 번에 출력")
    parser.add_argument("--out", type=str, metavar="FILE", help="결과를 UTF-8 파일로 저장 (예: --out result.txt)")
    args = parser.parse_args()

    if args.demo:
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                old = sys.stdout
                sys.stdout = f
                try:
                    run_demo()
                finally:
                    sys.stdout = old
            print(f"데모 결과를 저장했습니다: {args.out}")
        else:
            run_demo()
        return

    if args.issue:
        issues = [args.issue.strip()]
    else:
        issues = list(PRIMARY_ISSUES)

    def run_checks():
        print("=" * 70)
        print("결론 단계 판례 데이터 로딩 검증")
        print("=" * 70)
        print(f"이슈 개수: {len(issues)}, 키워드당 최대 판례: {args.max}\n")
        for issue in issues:
            precedents, meta = get_precedents_from_cache_with_meta(issue, max_results=args.max)
            keyword_used = meta.get("keyword_used", "")
            path_used = meta.get("path_used", "")
            count = meta.get("count", 0)
            titles = meta.get("titles", [])
            ids = meta.get("precedent_ids", [])
            error = meta.get("error", "")
            print(f"[이슈] {issue}")
            print(f"  사용 키워드: {keyword_used!r}")
            print(f"  캐시 경로:   {path_used or '(없음)'}")
            if error:
                print(f"  오류:        {error}")
            print(f"  로딩 건수:   {count}건")
            if titles:
                print("  사건명(상위):")
                for i, t in enumerate(titles[:10], 1):
                    short = (t[:60] + "…") if len(t) > 60 else t
                    print(f"    {i}. {short}")
                if len(titles) > 10:
                    print(f"    ... 외 {len(titles) - 10}건")
            if ids and count <= 10:
                print(f"  판례일련번호: {ids}")
            print()
        print("=" * 70)
        print("검증 완료. 위에서 각 이슈별로 사용된 키워드·경로·사건명이 해당 이슈와 맞는지 확인하세요.")
        print("=" * 70)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            old_stdout, sys.stdout = sys.stdout, f
            try:
                run_checks()
            finally:
                sys.stdout = old_stdout
        print(f"결과를 저장했습니다: {args.out}")
    else:
        run_checks()


if __name__ == "__main__":
    main()
