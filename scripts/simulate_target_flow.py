# -*- coding: utf-8 -*-
"""
시뮬레이션: 실제 챗봇 플로우 (상황 → 이슈 → 체크리스트 → 결론)
STEP2(타겟 질문) 제거됨. 이슈 선택 후 바로 체크리스트로 진행.

조문 목록: API 동기화된 근로기준법 본문(api_chapters)에서 로드.
API 키 있으면: 전체 플로우(이슈분류 → 체크리스트 → 결론) 실행.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.pipeline import (
    step1_issue_classification,
    step2_checklist,
    step3_conclusion,
)


def articles_from_api(max_items: int = 50):
    """API 동기화된 근로기준법 본문에서 조문 목록 생성. sync_laws 필요."""
    from rag.api_chapters import get_articles_by_chapter_from_api, get_chapters_from_api
    out = []
    for ch in get_chapters_from_api():
        num = ch.get("number", "")
        arts = get_articles_by_chapter_from_api(num)
        if arts:
            for a in arts:
                an = a.get("article_number", "")
                if an:
                    out.append({"article": an})
                    if len(out) >= max_items:
                        return out
    return out


def run_full_simulation(situation: str = "퇴직금을 받지 못했어요"):
    """전체 플로우 (이슈분류 → 체크리스트 → 결론). API 키 필요."""
    from config import SOURCE_LAW
    from rag.store import build_vector_store, search

    print("=" * 60)
    print(f"전체 시뮬레이션: 「{situation}」")
    print("=" * 60)

    collection, _ = build_vector_store()
    issues, articles_by_issue, _ = step1_issue_classification(situation, collection=collection)
    if not issues:
        print("이슈 없음.")
        return False
    issue = issues[0]
    print(f"[1] 이슈: {issue}")

    pre_selected = list(articles_by_issue.get(issue, []))
    if not pre_selected:
        seen = set()
        for q in [issue, situation]:
            res = search(
                collection, q, top_k=18,
                filter_sources=[SOURCE_LAW],
                exclude_sections=["벌칙", "부칙"],
                exclude_chapters=["제1장 총칙"],
            )
            for r in res:
                art = r.get("article", "")
                if art and art not in seen:
                    pre_selected.append(r)
                    seen.add(art)
    print(f"    조문 수: {len(pre_selected)}")

    qa_list = []
    filter_text = (situation + " " + issue)[:500]
    step2_res = step2_checklist(
        issue, filter_text, collection=collection,
        narrow_answers=None, qa_list=qa_list, remaining_articles=pre_selected,
    )
    checklist = step2_res.get("checklist", []) if isinstance(step2_res, dict) else (step2_res or [])
    print(f"[2] 체크리스트: {len(checklist)}개")

    res = step3_conclusion(issue, qa_list, collection=collection, narrow_answers=None)
    conclusion = res.get("conclusion", "") if isinstance(res, dict) else str(res)
    print(f"[3] 결론: {len(conclusion)}자")
    print("=" * 60)
    return bool(conclusion)


if __name__ == "__main__":
    has_api = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    if has_api:
        ok = run_full_simulation("퇴직금을 받지 못했어요")
        sys.exit(0 if ok else 1)
    else:
        print("OPENAI_API_KEY 없음 → 전체 플로우 생략.")
        sys.exit(0)
