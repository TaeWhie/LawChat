# -*- coding: utf-8 -*-
"""실제 RAG 답변 품질 확인 - 간단 버전"""

import re
from rag.store import build_vector_store, search
from rag.pipeline import _rag_context
from rag.question_classifier import (
    classify_question_type,
    calculate_severance_pay,
    calculate_overtime_pay,
)
from config import ALL_LABOR_LAW_SOURCES


def test_severance_pattern():
    """퇴직금 패턴 매칭 테스트"""
    test_question = "2022년 1월 1일에 입사해서 2024년 2월 28일에 퇴사했어. 월급은 300만 원이었는데 퇴직금 대략 얼마야?"
    
    patterns = [
        r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?(\d+)[만천백]?\s*원",
        r"입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?퇴사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?월급.*?(\d+)[만천백]?\s*원",
        r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?월급.*?(\d+)[만천백]?\s*원",
    ]
    
    print(f"질문: {test_question}\n")
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, test_question, re.IGNORECASE)
        if match:
            print(f"✅ 패턴 {i} 매칭 성공: {match.groups()}")
            if len(match.groups()) >= 7:
                try:
                    start_date = f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
                    end_date = f"{match.group(4)}-{match.group(5).zfill(2)}-{match.group(6).zfill(2)}"
                    monthly_salary = float(match.group(7)) * 10000
                    result = calculate_severance_pay(start_date, end_date, monthly_salary)
                    if result.get("success"):
                        print(f"   계산 결과: {result['estimated_severance']:,}원")
                        return True
                except Exception as e:
                    print(f"   계산 실패: {e}")
        else:
            print(f"❌ 패턴 {i} 매칭 실패")
    
    return False


def test_overtime_pattern():
    """연장근로 패턴 매칭 테스트"""
    test_question = "오늘 8시간 근무하고 밤에 2시간 더 일했어. 시급이 만 원이면 오늘 총 얼마 받아야 해?"
    
    patterns = [
        r"(\d+)시간.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
        r"(\d+)시간.*?근무.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
        r"(\d+)시간.*?(\d+)시간.*?시급.*?(\d+)[만천백]?\s*원",
        r"(\d+)시간.*?일했어.*?시급.*?(\d+)[만천백]?\s*원",
    ]
    
    print(f"\n질문: {test_question}\n")
    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, test_question, re.IGNORECASE)
        if match:
            print(f"✅ 패턴 {i} 매칭 성공: {match.groups()}")
            if len(match.groups()) >= 3:
                try:
                    base_hours = int(match.group(1))
                    overtime_hours = int(match.group(2))
                    hourly_wage = int(match.group(3)) * 10000
                    result = calculate_overtime_pay(base_hours, overtime_hours, hourly_wage)
                    if result.get("success"):
                        print(f"   계산 결과: {result['total_pay']:,}원")
                        return True
                except Exception as e:
                    print(f"   계산 실패: {e}")
        else:
            print(f"❌ 패턴 {i} 매칭 실패")
    
    return False


def test_rag_search():
    """RAG 검색 품질 테스트"""
    print("\n" + "="*60)
    print("RAG 검색 품질 테스트")
    print("="*60)
    
    collection, _ = build_vector_store()
    
    test_cases = [
        ("지식 질문", "통상임금과 평균임금의 차이가 뭐야?"),
        ("계산 질문", "퇴직금 계산 방법"),
        ("상황 질문", "부당해고 당했어요"),
    ]
    
    for category, question in test_cases:
        print(f"\n[{category}] {question}")
        results = search(
            collection, question, top_k=3,
            filter_sources=ALL_LABOR_LAW_SOURCES,
            exclude_sections=["벌칙", "부칙"],
        )
        
        if results:
            print(f"✅ 검색 성공: {len(results)}개 조문")
            for i, r in enumerate(results[:3], 1):
                print(f"   {i}. {r.get('article', 'N/A')} - {r.get('text', '')[:50]}...")
            
            # 컨텍스트 생성 테스트
            context = _rag_context(results, max_length=1000)
            print(f"   컨텍스트 길이: {len(context)}자")
        else:
            print("❌ 검색 결과 없음")


if __name__ == "__main__":
    print("="*60)
    print("답변 품질 시뮬레이션")
    print("="*60)
    
    print("\n1. 퇴직금 패턴 매칭 테스트")
    print("-"*60)
    test_severance_pattern()
    
    print("\n2. 연장근로 패턴 매칭 테스트")
    print("-"*60)
    test_overtime_pattern()
    
    print("\n3. RAG 검색 품질 테스트")
    test_rag_search()
    
    print("\n" + "="*60)
    print("시뮬레이션 완료")
    print("="*60)
    print("\n💡 실제 LLM 답변 품질을 확인하려면:")
    print("   - test_rag_answers.py 실행 (LLM 호출 필요)")
    print("   - 또는 app_chatbot.py에서 실제 질문 테스트")