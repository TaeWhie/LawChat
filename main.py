"""
노동법 RAG 챗봇 - 파이프라인 실행
1. 상황 입력 → RAG 기반 이슈 분류(멀티 이슈)
2. 체크리스트 생성(숫자·요건 확인)
3. Q&A 기반 결론 (법조항 인용)
"""
import sys
from config import ALL_LABOR_LAW_SOURCES
from rag import (
    build_vector_store,
    step1_issue_classification,
    step2_checklist,
    step3_conclusion,
)
from rag.store import search
from rag.law_json import filter_articles_by_issue_relevance
from config import RAG_MAIN_TOP_K, RAG_FILTER_TOP_K


def main(force_rebuild: bool = False):
    print("노동법 RAG 챗봇 (근로기준법 등)")
    print("벡터 스토어 준비 중...")
    collection, was_built = build_vector_store(force_rebuild=force_rebuild)
    if was_built:
        print("벡터 스토어를 새로 구축했습니다 (임베딩 완료). 다음 실행부터는 vector_store/ 를 재사용합니다.")
    else:
        print("기존 vector_store/ 를 사용합니다 (재임베딩 없음).")
    print("준비 완료.\n")

    print("상황을 입력해 주세요 (예: 회사에서 30일 통보 없이 해고당했어요):")
    situation = input("> ").strip()
    if not situation:
        print("상황이 비어 있습니다. 종료합니다.")
        sys.exit(1)

    # 1. 이슈 분류 (이슈 + 이슈별 조문 반환)
    print("\n[1단계] 상황에 따른 이슈 분류 중...")
    issues, articles_by_issue, _ = step1_issue_classification(situation, collection=collection)
    if not issues:
        print("제공된 법령 데이터에서 해당 상황에 맞는 이슈를 찾지 못했습니다.")
        sys.exit(0)
    print("감지된 이슈:", ", ".join(issues))

    issue = issues[0]
    if len(issues) > 1:
        print(f"먼저 '{issue}' 이슈로 진행합니다.\n")

    # 2. step1에서 받은 이슈별 조문 사용, 없으면 검색 (Streamlit과 동일: 전체 노동법 대상)
    remaining = list(articles_by_issue.get(issue, []))
    if not remaining:
        seen = set()
        for q in [issue, situation]:
            res = search(
                collection, q, top_k=RAG_MAIN_TOP_K,
                filter_sources=ALL_LABOR_LAW_SOURCES,
                exclude_sections=["벌칙", "부칙"],
                exclude_chapters=["제1장 총칙"],
            )
            for r in res:
                art = r.get("article", "")
                if art and art not in seen:
                    remaining.append(r)
                    seen.add(art)
    remaining = filter_articles_by_issue_relevance(issue, remaining, top_k=RAG_FILTER_TOP_K)
    print(f"  조문 {len(remaining)}개 확정")

    # 3. 체크리스트
    print("\n[2단계] 체크리스트 생성 중...")
    qa_list = []
    filter_text = (situation + " " + issue)[:500]
    step2_res = step2_checklist(
        issue, filter_text, collection=collection,
        narrow_answers=None,
        qa_list=qa_list,
        remaining_articles=remaining,
    )
    checklist = step2_res.get("checklist", []) if isinstance(step2_res, dict) else (step2_res or [])
    if checklist:
        print("\n요건 검사용 체크리스트:")
        for i, item in enumerate(checklist, 1):
            q = item.get("question") or item.get("item") or str(item)
            print(f"  {i}. {q}")
            a = input("  답변> ").strip()
            qa_list.append({"question": q, "answer": a or "(미입력)"})
    else:
        print("체크리스트가 생성되지 않았습니다.")

    # 4. 결론
    print("\n[3단계] 결론 생성 중...")
    narrow_answers = [x.get("answer", "").strip() for x in qa_list if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "(미입력)")]
    res = step3_conclusion(issue, qa_list, collection=collection, narrow_answers=narrow_answers or None)
    conclusion = res.get("conclusion", res) if isinstance(res, dict) else res
    related = res.get("related_articles", []) if isinstance(res, dict) else []
    print("\n" + "=" * 60)
    print("결론")
    print("=" * 60)
    print(conclusion)
    if related:
        print("\n📎 함께 확인해 보세요:", ", ".join(related))
    print("=" * 60)


if __name__ == "__main__":
    force_rebuild = "--rebuild" in sys.argv or "-r" in sys.argv
    if force_rebuild:
        print("벡터 스토어 재구축 모드")
    main(force_rebuild)
