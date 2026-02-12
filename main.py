"""
노동법 RAG 챗봇 - 파이프라인 실행
1. 상황 입력 → RAG 기반 이슈 분류(멀티 이슈)
2. 이슈별 조항 좁히기 → 구분 질문
3. 체크리스트 생성(정확한 숫자·요건 검사)
4. Q&A 기반 결론 (법조항 인용)
"""
import sys
from rag import (
    build_vector_store,
    step1_issue_classification,
    step2_provision_narrow,
    step3_checklist,
    step4_conclusion,
)


def main(force_rebuild: bool = False):
    print("노동법 RAG 챗봇 (근로기준법 등)")
    print("벡터 스토어 준비 중...")
    collection = build_vector_store(force_rebuild=force_rebuild)
    print("준비 완료.\n")

    print("상황을 입력해 주세요 (예: 회사에서 30일 통보 없이 해고당했어요):")
    situation = input("> ").strip()
    if not situation:
        print("상황이 비어 있습니다. 종료합니다.")
        sys.exit(1)

    # 1. 이슈 분류
    print("\n[1단계] 상황에 따른 이슈 분류 중...")
    issues = step1_issue_classification(situation, collection=collection)
    if not issues:
        print("제공된 법령 데이터에서 해당 상황에 맞는 이슈를 찾지 못했습니다.")
        sys.exit(0)
    print("감지된 이슈:", ", ".join(issues))

    # 첫 번째 이슈로 진행 (여러 이슈면 사용자가 선택하도록 확장 가능)
    issue = issues[0]
    if len(issues) > 1:
        print(f"먼저 '{issue}' 이슈로 진행합니다. (다른 이슈는 추후 확장 예정)\n")

    # 2. 조항 좁히기 + 구분 질문
    print("\n[2단계] 해당 이슈 관련 조항 구분을 위한 질문 생성 중...")
    narrow = step2_provision_narrow(issue, collection=collection)
    categories = narrow.get("categories", [])
    questions = narrow.get("questions", [])
    if categories:
        print("관련 조항 카테고리:", ", ".join(categories))
    qa_list = []
    if questions:
        print("\n다음 질문에 답해 주세요 (조항 구분용):")
        for i, q in enumerate(questions, 1):
            a = input(f"  Q{i}. {q}\n  A> ").strip()
            qa_list.append({"question": q, "answer": a or "(미입력)"})
    else:
        print("구분 질문이 생성되지 않았습니다. 이슈만으로 체크리스트를 생성합니다.")

    # 걸러진 조항 요약 = 구분 질문에 대한 답변
    filtered_text = "\n".join(f"Q: {x['question']}\nA: {x['answer']}" for x in qa_list) if qa_list else issue

    # 3. 체크리스트
    print("\n[3단계] 체크리스트 생성 중...")
    checklist = step3_checklist(issue, filtered_text, collection=collection)
    if checklist:
        print("\n요건 검사용 체크리스트 (숫자·기간 등 확인):")
        for i, item in enumerate(checklist, 1):
            q = item.get("question") or item.get("item") or str(item)
            print(f"  {i}. {q}")
            a = input("  답변> ").strip()
            qa_list.append({"question": q, "answer": a or "(미입력)"})
    else:
        print("체크리스트가 생성되지 않았습니다.")

    # 4. 결론
    print("\n[4단계] 결론 생성 중...")
    conclusion = step4_conclusion(issue, qa_list, collection=collection)
    print("\n" + "=" * 60)
    print("결론")
    print("=" * 60)
    print(conclusion)
    print("=" * 60)


if __name__ == "__main__":
    force_rebuild = "--rebuild" in sys.argv or "-r" in sys.argv
    if force_rebuild:
        print("벡터 스토어 재구축 모드")
    main(force_rebuild)
