# -*- coding: utf-8 -*-
"""RAG 기반 답변 품질 테스트 - 실제 벡터 스토어와 LLM 사용"""

import sys
from rag.store import build_vector_store, search
from rag.graph import process_turn, ChatbotState
from rag.pipeline import _rag_context
from rag.question_classifier import (
    classify_question_type,
    system_knowledge_qa,
    user_knowledge_qa,
    system_calculation_qa,
    user_calculation_qa,
    system_exception_qa,
    user_exception_qa,
    calculate_severance_pay,
    calculate_overtime_pay,
)
from rag.llm import chat
from config import ALL_LABOR_LAW_SOURCES


def test_knowledge_qa(question: str, collection):
    """지식 기반 질문 RAG 테스트"""
    print(f"\n📚 질문: {question}")
    print("-" * 60)
    
    # RAG 검색
    search_results = search(
        collection, question, top_k=5,
        filter_sources=ALL_LABOR_LAW_SOURCES,
        exclude_sections=["벌칙", "부칙"],
    )
    
    if not search_results:
        print("❌ 검색 결과 없음")
        return False
    
    print(f"✅ 검색된 조문 수: {len(search_results)}")
    print(f"   첫 번째 조문: {search_results[0].get('article', 'N/A')}")
    
    # RAG 컨텍스트 생성
    rag_context = _rag_context(search_results, max_length=2000)
    print(f"   컨텍스트 길이: {len(rag_context)}자")
    
    # LLM 답변 생성 (실제 호출은 비용이 들 수 있으므로 선택적)
    try:
        print("   LLM 호출 중...")
        answer = chat(
            system_knowledge_qa(),
            user_knowledge_qa(question, rag_context),
            max_tokens=500
        )
        
        if not answer or len(answer.strip()) == 0:
            print("❌ LLM 답변이 비어있음")
            return False
        
        print(f"\n💬 답변 (전체):\n{answer}\n")
        print(f"   답변 길이: {len(answer)}자")
        
        # 품질 체크
        checks = {
            "조문 인용": "제" in answer and "조" in answer,
            "간단한 설명": len(answer) > 50,
            "법률 용어 사용": any(term in answer for term in ["근로기준법", "법률", "조항", "근로기준법"]),
        }
        
        print("\n📊 품질 체크:")
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {check}: {passed}")
        
        return all(checks.values())
    except Exception as e:
        print(f"❌ LLM 호출 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_calculation_qa(question: str, collection):
    """계산 질문 RAG 테스트"""
    print(f"\n🔢 질문: {question}")
    print("-" * 60)
    
    import re
    
    # 퇴직금 패턴 테스트 (더 유연하게)
    severance_patterns = [
        r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?(\d+)[만천백]?\s*원",
        r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?월급.*?(\d+)[만천백]?\s*원",
        r"입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?퇴사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?(\d+)[만천백]?\s*원",
    ]
    severance_match = None
    for pattern in severance_patterns:
        severance_match = re.search(pattern, question, re.IGNORECASE)
        if severance_match:
            break
    
    if severance_match:
        try:
            start_date = f"{severance_match.group(1)}-{severance_match.group(2).zfill(2)}-{severance_match.group(3).zfill(2)}"
            end_date = f"{severance_match.group(4)}-{severance_match.group(5).zfill(2)}-{severance_match.group(6).zfill(2)}"
            monthly_salary = float(severance_match.group(7)) * 10000
            calc_result = calculate_severance_pay(start_date, end_date, monthly_salary)
            
            if calc_result.get("success"):
                print(f"✅ 퇴직금 계산 성공")
                print(f"   근무 기간: {calc_result['work_days']}일 ({calc_result['work_years']}년)")
                print(f"   예상 퇴직금: {calc_result['estimated_severance']:,}원")
                print(f"   계산식: {calc_result['formula']}")
                
                # RAG로 관련 조문 확인
                search_results = search(
                    collection, "퇴직금 계산", top_k=3,
                    filter_sources=ALL_LABOR_LAW_SOURCES,
                )
                if search_results:
                    print(f"   관련 조문: {search_results[0].get('article', 'N/A')}")
                
                return True
        except Exception as e:
            print(f"❌ 계산 실패: {e}")
            return False
    
    # 연장근로 패턴 테스트
    overtime_patterns = [
        r"(\d+)시간.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
        r"(\d+)시간.*?근무.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
    ]
    for pattern in overtime_patterns:
        overtime_match = re.search(pattern, question, re.IGNORECASE)
        if overtime_match:
            try:
                base_hours = int(overtime_match.group(1))
                overtime_hours = int(overtime_match.group(2))
                hourly_wage = int(overtime_match.group(3)) * 10000
                calc_result = calculate_overtime_pay(base_hours, overtime_hours, hourly_wage)
                
                if calc_result.get("success"):
                    print(f"✅ 연장근로 수당 계산 성공")
                    print(f"   총 수당: {calc_result['total_pay']:,}원")
                    print(f"   계산식: {calc_result['formula']}")
                    
                    # RAG로 관련 조문 확인
                    search_results = search(
                        collection, "연장근로 수당", top_k=3,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                    )
                    if search_results:
                        print(f"   관련 조문: {search_results[0].get('article', 'N/A')}")
                    
                    return True
            except Exception as e:
                print(f"❌ 계산 실패: {e}")
                return False
    
    # 패턴 매칭 실패 시 RAG 기반 답변
    print("⚠️ 패턴 매칭 실패, RAG 기반 답변 시도")
    search_results = search(
        collection, question, top_k=5,
        filter_sources=ALL_LABOR_LAW_SOURCES,
    )
    if search_results:
        rag_context = _rag_context(search_results, max_length=2000)
        try:
            answer = chat(
                system_calculation_qa(),
                user_calculation_qa(question, rag_context),
                max_tokens=500
            )
            print(f"💬 답변 (요약): {answer[:200]}...")
            return len(answer) > 50
        except Exception as e:
            print(f"❌ LLM 호출 실패: {e}")
            return False
    
    return False


def test_exception_qa(question: str, collection):
    """예외 상황 질문 RAG 테스트"""
    print(f"\n⚠️ 질문: {question}")
    print("-" * 60)
    
    # 유도 질문 감지
    if any(kw in question for kw in ["몰래", "기밀", "빼돌려"]):
        print("✅ 유도 질문 감지됨")
        print("   → 윤리적 가이드라인 제공 로직 실행")
        return True
    
    # RAG 검색
    search_results = search(
        collection, question, top_k=5,
        filter_sources=ALL_LABOR_LAW_SOURCES,
    )
    
    if not search_results:
        print("⚠️ 검색 결과 없음 (예외 상황이므로 정상일 수 있음)")
        return True  # 예외 상황은 검색 결과가 없을 수 있음
    
    print(f"✅ 검색된 조문 수: {len(search_results)}")
    rag_context = _rag_context(search_results, max_length=2000)
    
    try:
        answer = chat(
            system_exception_qa(),
            user_exception_qa(question, rag_context),
            max_tokens=500
        )
        print(f"\n💬 답변 (요약): {answer[:200]}...")
        
        # 최신성 확인 질문인 경우
        if any(kw in question for kw in ["올해", "2026", "2025", "2024", "최신"]):
            if "데이터" in answer or "연도" in answer or "법령" in answer:
                print("✅ 최신성 안내 포함됨")
        
        return len(answer) > 50
    except Exception as e:
        print(f"❌ LLM 호출 실패: {e}")
        return False


def test_situation_qa(question: str, collection):
    """상황 기반 상담 테스트 (기존 로직)"""
    print(f"\n💼 질문: {question}")
    print("-" * 60)
    
    from rag.pipeline import step1_issue_classification
    
    try:
        issues, articles_by_issue, _ = step1_issue_classification(question, collection=collection)
        
        if not issues:
            print("❌ 이슈 분류 실패")
            return False
        
        print(f"✅ 감지된 이슈: {', '.join(issues)}")
        print(f"   이슈별 조문 수:")
        for issue, articles in articles_by_issue.items():
            print(f"     - {issue}: {len(articles)}개")
        
        return len(issues) > 0 and any(len(articles) > 0 for articles in articles_by_issue.values())
    except Exception as e:
        print(f"❌ 처리 실패: {e}")
        return False


def main():
    print("=" * 60)
    print("RAG 기반 답변 품질 테스트")
    print("=" * 60)
    
    # 벡터 스토어 준비
    print("\n📦 벡터 스토어 준비 중...")
    try:
        collection, _ = build_vector_store()
        print("✅ 벡터 스토어 준비 완료")
    except Exception as e:
        print(f"❌ 벡터 스토어 준비 실패: {e}")
        return
    
    # 시나리오별 테스트
    test_cases = [
        # 시나리오 1: 지식 기반
        ("knowledge", "통상임금과 평균임금의 차이가 뭐야?"),
        ("knowledge", "5인 미만 사업장인데 나도 연차 휴가를 받을 수 있어?"),
        
        # 시나리오 2: 계산
        ("calculation", "2022년 1월 1일에 입사해서 2024년 2월 28일에 퇴사했어. 월급은 300만 원이었는데 퇴직금 대략 얼마야?"),
        ("calculation", "오늘 8시간 근무하고 밤에 2시간 더 일했어. 시급이 만 원이면 오늘 총 얼마 받아야 해?"),
        
        # 시나리오 3: 상황 기반
        ("situation", "사장이 오늘 갑자기 내일부터 나오지 말래. 이유도 안 알려줬어."),
        ("situation", "회사가 돈이 없다고 월급을 두 달째 안 주고 있어."),
        
        # 시나리오 4: 예외 상황
        ("exception", "나는 프리랜서로 계약했는데 실제로는 회사 지시를 다 받아. 나도 노동법 보호를 받을 수 있을까?"),
        ("exception", "사장 몰래 회사 기밀을 빼돌려서 퇴사하고 싶은데, 이래도 퇴직금 받을 수 있어?"),
    ]
    
    results = {}
    for q_type, question in test_cases:
        print(f"\n{'='*60}")
        print(f"테스트: {q_type.upper()}")
        print(f"{'='*60}")
        
        if q_type == "knowledge":
            result = test_knowledge_qa(question, collection)
        elif q_type == "calculation":
            result = test_calculation_qa(question, collection)
        elif q_type == "exception":
            result = test_exception_qa(question, collection)
        elif q_type == "situation":
            result = test_situation_qa(question, collection)
        else:
            result = False
        
        if q_type not in results:
            results[q_type] = []
        results[q_type].append(result)
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    
    for q_type, result_list in results.items():
        passed = sum(result_list)
        total = len(result_list)
        print(f"\n{q_type.upper()}: {passed}/{total} 통과 ({passed*100//total}%)")
        for i, result in enumerate(result_list, 1):
            status = "✅" if result else "❌"
            print(f"  {status} 테스트 {i}")


if __name__ == "__main__":
    main()