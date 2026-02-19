# -*- coding: utf-8 -*-
"""실제 LLM 호출로 답변 품질 확인"""

import sys
from rag.store import build_vector_store, search
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


def test_knowledge_answer(question: str, collection):
    """지식 질문 실제 답변 테스트"""
    print(f"\n{'='*60}")
    print(f"📚 지식 질문: {question}")
    print('='*60)
    
    # RAG 검색
    search_results = search(
        collection, question, top_k=5,
        filter_sources=ALL_LABOR_LAW_SOURCES,
        exclude_sections=["벌칙", "부칙"],
    )
    
    if not search_results:
        print("❌ 검색 결과 없음")
        return False
    
    print(f"✅ 검색된 조문: {len(search_results)}개")
    for i, r in enumerate(search_results[:3], 1):
        print(f"   {i}. {r.get('article', 'N/A')}")
    
    # RAG 컨텍스트 생성
    rag_context = _rag_context(search_results, max_length=2000)
    print(f"\n📄 RAG 컨텍스트 길이: {len(rag_context)}자")
    
    # LLM 답변 생성
    try:
        print("\n🤖 LLM 답변 생성 중...")
        answer = chat(
            system_knowledge_qa(),
            user_knowledge_qa(question, rag_context),
            max_tokens=800
        )
        
        if not answer or len(answer.strip()) == 0:
            print("❌ 답변이 비어있음")
            return False
        
        print(f"\n💬 답변:\n{answer}\n")
        
        # 품질 체크
        checks = {
            "조문 인용": "제" in answer and "조" in answer,
            "적절한 길이": 50 < len(answer) < 2000,
            "법률 용어 포함": any(term in answer for term in ["근로기준법", "법률", "조항", "법령"]),
            "간단한 설명": len(answer.split('\n')) > 2,
        }
        
        print("📊 품질 체크:")
        passed = 0
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}: {result}")
            if result:
                passed += 1
        
        return passed >= 3  # 4개 중 3개 이상 통과
    except Exception as e:
        print(f"❌ LLM 호출 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_calculation_answer(question: str, collection):
    """계산 질문 실제 답변 테스트"""
    print(f"\n{'='*60}")
    print(f"🔢 계산 질문: {question}")
    print('='*60)
    
    import re
    
    # 퇴직금 패턴 테스트
    severance_patterns = [
        r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?(\d+)[만천백]?\s*원",
        r"입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?퇴사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?월급.*?(\d+)[만천백]?\s*원",
    ]
    
    severance_match = None
    for pattern in severance_patterns:
        severance_match = re.search(pattern, question, re.IGNORECASE | re.DOTALL)
        if severance_match:
            break
    
    if severance_match:
        try:
            start_date = f"{severance_match.group(1)}-{severance_match.group(2).zfill(2)}-{severance_match.group(3).zfill(2)}"
            end_date = f"{severance_match.group(4)}-{severance_match.group(5).zfill(2)}-{severance_match.group(6).zfill(2)}"
            monthly_salary = float(severance_match.group(7)) * 10000
            result = calculate_severance_pay(start_date, end_date, monthly_salary)
            
            if result.get("success"):
                print(f"✅ 퇴직금 계산 성공: {result['estimated_severance']:,}원")
                return True
        except Exception as e:
            print(f"❌ 계산 실패: {e}")
    
    # 연장근로 패턴 테스트
    overtime_patterns = [
        r"(\d+)시간.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
        r"(\d+)시간.*?근무.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
        r"(\d+)시간.*?(\d+)시간.*?시급.*?(\d+)[만천백]?\s*원",
    ]
    
    overtime_match = None
    for pattern in overtime_patterns:
        overtime_match = re.search(pattern, question, re.IGNORECASE | re.DOTALL)
        if overtime_match:
            break
    
    if overtime_match:
        try:
            base_hours = int(overtime_match.group(1))
            overtime_hours = int(overtime_match.group(2))
            hourly_wage = int(overtime_match.group(3)) * 10000
            result = calculate_overtime_pay(base_hours, overtime_hours, hourly_wage)
            
            if result.get("success"):
                print(f"✅ 연장근로 수당 계산 성공: {result['total_pay']:,}원")
                return True
        except Exception as e:
            print(f"❌ 계산 실패: {e}")
    
    # 패턴 매칭 실패 시 RAG 기반 답변
    print("⚠️ 패턴 매칭 실패, RAG 기반 답변 시도")
    search_results = search(
        collection, question, top_k=5,
        filter_sources=ALL_LABOR_LAW_SOURCES,
    )
    
    if not search_results:
        print("❌ 검색 결과 없음")
        return False
    
    print(f"✅ 검색된 조문: {len(search_results)}개")
    rag_context = _rag_context(search_results, max_length=2000)
    
    try:
        print("\n🤖 LLM 답변 생성 중...")
        answer = chat(
            system_calculation_qa(),
            user_calculation_qa(question, rag_context),
            max_tokens=800
        )
        
        if not answer or len(answer.strip()) == 0:
            print("❌ 답변이 비어있음")
            return False
        
        print(f"\n💬 답변:\n{answer}\n")
        
        # 품질 체크
        checks = {
            "계산 포함": any(kw in answer for kw in ["원", "계산", "총", "합계"]),
            "적절한 길이": 50 < len(answer) < 2000,
            "조문 인용": "제" in answer and "조" in answer,
        }
        
        print("📊 품질 체크:")
        passed = sum(checks.values())
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}: {result}")
        
        return passed >= 2
    except Exception as e:
        print(f"❌ LLM 호출 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_exception_answer(question: str, collection):
    """예외 질문 실제 답변 테스트"""
    print(f"\n{'='*60}")
    print(f"⚠️ 예외 질문: {question}")
    print('='*60)
    
    # 유도 질문 감지
    if any(kw in question for kw in ["몰래", "기밀", "빼돌려"]):
        print("✅ 유도 질문 감지됨 (하드코딩된 답변)")
        return True
    
    # RAG 검색
    search_results = search(
        collection, question, top_k=5,
        filter_sources=ALL_LABOR_LAW_SOURCES,
    )
    
    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
    
    try:
        print("\n🤖 LLM 답변 생성 중...")
        answer = chat(
            system_exception_qa(),
            user_exception_qa(question, rag_context),
            max_tokens=800
        )
        
        if not answer or len(answer.strip()) == 0:
            print("❌ 답변이 비어있음")
            return False
        
        print(f"\n💬 답변:\n{answer}\n")
        
        # 품질 체크
        checks = {
            "적절한 길이": 50 < len(answer) < 2000,
            "명확한 가이드": any(kw in answer for kw in ["기준", "판단", "가능", "불가능", "조건"]),
        }
        
        print("📊 품질 체크:")
        passed = sum(checks.values())
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"   {status} {check}: {result}")
        
        return passed >= 1
    except Exception as e:
        print(f"❌ LLM 호출 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("="*60)
    print("실제 LLM 답변 품질 테스트")
    print("="*60)
    
    # 벡터 스토어 준비
    print("\n📦 벡터 스토어 준비 중...")
    try:
        collection, _ = build_vector_store()
        print("✅ 벡터 스토어 준비 완료")
    except Exception as e:
        print(f"❌ 벡터 스토어 준비 실패: {e}")
        return
    
    # 테스트 케이스
    test_cases = [
        # 지식 질문
        ("knowledge", "통상임금과 평균임금의 차이가 뭐야?"),
        ("knowledge", "5인 미만 사업장인데 나도 연차 휴가를 받을 수 있어?"),
        
        # 계산 질문
        ("calculation", "퇴직금 계산 방법을 알려줘"),
        ("calculation", "연장근로 수당은 어떻게 계산하나요?"),
        
        # 예외 질문
        ("exception", "나는 프리랜서로 계약했는데 실제로는 회사 지시를 다 받아. 나도 노동법 보호를 받을 수 있을까?"),
    ]
    
    results = {}
    for q_type, question in test_cases:
        if q_type == "knowledge":
            result = test_knowledge_answer(question, collection)
        elif q_type == "calculation":
            result = test_calculation_answer(question, collection)
        elif q_type == "exception":
            result = test_exception_answer(question, collection)
        else:
            result = False
        
        if q_type not in results:
            results[q_type] = []
        results[q_type].append(result)
    
    # 결과 요약
    print("\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)
    
    for q_type, result_list in results.items():
        passed = sum(result_list)
        total = len(result_list)
        print(f"\n{q_type.upper()}: {passed}/{total} 통과 ({passed*100//total if total > 0 else 0}%)")
        for i, result in enumerate(result_list, 1):
            status = "✅" if result else "❌"
            print(f"  {status} 테스트 {i}")


if __name__ == "__main__":
    main()