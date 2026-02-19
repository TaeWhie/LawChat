# -*- coding: utf-8 -*-
"""한 번만 전체 플로우 시뮬레이션 (상황 인자 또는 기본값)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv()

from config import SOURCE_LAW
from rag.store import build_vector_store, search
from rag.pipeline import step1_issue_classification, step2_checklist, step3_conclusion

def main():
    situation = sys.argv[1] if len(sys.argv) > 1 else "월급을 받지 못했어요"
    print("=" * 60)
    print("시뮬레이션 상황:", situation)
    print("=" * 60)

    collection, was_built = build_vector_store()
    n = collection.count()
    print("[벡터 스토어] 문서 수:", n, "| was_built:", was_built)

    if n == 0:
        print("벡터 스토어가 비어 있습니다. scripts/rebuild_vector_store.py 를 먼저 실행하세요.")
        return 1

    # Step1 (이슈 + 이슈별 조문 반환)
    print("\n[Step1] 이슈 분류 중...")
    issues, articles_by_issue, _ = step1_issue_classification(situation, collection=collection)
    if not issues:
        print("  -> 이슈 없음 (검색 결과 0건)")
        return 1
    print("  -> 이슈:", ", ".join(issues))
    issue = issues[0]

    # step1 조문 사용, 없으면 검색
    print("\n[조문 검색]")
    pre_selected = list(articles_by_issue.get(issue, []))
    if not pre_selected:
        seen = set()
        for q in [issue, situation]:
            res = search(collection, q, top_k=18, filter_sources=[SOURCE_LAW],
                         exclude_sections=["벌칙", "부칙"], exclude_chapters=["제1장 총칙"])
            for r in res:
                art = r.get("article", "")
                if art and art not in seen:
                    pre_selected.append(r)
                    seen.add(art)
    print("  -> 조문", len(pre_selected), "개")

    # Step2 체크리스트 (이슈 선택 후 바로)
    print("\n[Step2] 체크리스트...")
    qa_list = []
    filter_text = (situation + " " + issue)[:500]
    step2_res = step2_checklist(issue, filter_text, collection=collection, narrow_answers=None, qa_list=qa_list, remaining_articles=pre_selected)
    checklist = step2_res.get("checklist", []) if isinstance(step2_res, dict) else (step2_res or [])
    print("  -> 체크리스트", len(checklist), "개")

    # Step3 결론
    print("\n[Step3] 결론 생성 중...")
    narrow_ans = [x.get("answer", "").strip() for x in qa_list if x.get("answer")]
    res = step3_conclusion(issue, qa_list, collection=collection, narrow_answers=narrow_ans or None)
    conclusion = res.get("conclusion", "") if isinstance(res, dict) else str(res)
    print("  -> 결론 길이:", len(conclusion), "자")
    print("\n--- 결론 (일부) ---")
    print(conclusion[:800] + "..." if len(conclusion) > 800 else conclusion)
    print("=" * 60)
    print("시뮬레이션 완료.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
