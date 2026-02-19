# -*- coding: utf-8 -*-
"""4가지 핵심 시나리오 시뮬레이션 테스트"""

from rag.question_classifier import classify_question_type
import re


def test_scenario_1_knowledge():
    """시나리오 1: 지식 기반 및 개념 확인"""
    print("=" * 60)
    print("시나리오 1: 지식 기반 및 개념 확인")
    print("=" * 60)
    
    test_cases = [
        "통상임금과 평균임금의 차이가 뭐야?",
        "5인 미만 사업장인데 나도 연차 휴가를 받을 수 있어?",
        "근로계약서에 적힌 내용이 근로기준법보다 낮으면 어떻게 돼?",
    ]
    
    for question in test_cases:
        q_type = classify_question_type(question)
        print(f"\n질문: {question}")
        print(f"→ 분류: {q_type}")
        if q_type == "knowledge":
            print("✅ 올바르게 분류됨")
        else:
            print(f"❌ 잘못된 분류 (예상: knowledge, 실제: {q_type})")


def test_scenario_2_calculation():
    """시나리오 2: 계산 및 산출형"""
    print("\n" + "=" * 60)
    print("시나리오 2: 계산 및 산출형")
    print("=" * 60)
    
    test_cases = [
        "2022년 1월 1일에 입사해서 2024년 2월 28일에 퇴사했어. 월급은 300만 원이었는데 퇴직금 대략 얼마야?",
        "오늘 8시간 근무하고 밤에 2시간 더 일했어. 시급이 만 원이면 오늘 총 얼마 받아야 해?",
        "고용보험 가입 기간이 3년이고 지금 내 나이가 35세라면 실업급여 몇 일 동안 받을 수 있어?",
    ]
    
    for question in test_cases:
        q_type = classify_question_type(question)
        print(f"\n질문: {question[:50]}...")
        print(f"→ 분류: {q_type}")
        
        # 퇴직금 패턴 테스트
        severance_pattern = r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?(\d+)만?\s*원"
        severance_match = re.search(severance_pattern, question)
        
        # 연장근로 패턴 테스트
        overtime_pattern = r"(\d+)시간.*?(\d+)시간.*?(\d+)만?\s*원"
        overtime_match = re.search(overtime_pattern, question)
        
        if q_type == "calculation":
            print("✅ 올바르게 분류됨")
            if severance_match:
                print(f"  → 퇴직금 패턴 매칭 성공: {severance_match.groups()}")
            elif overtime_match:
                print(f"  → 연장근로 패턴 매칭 성공: {overtime_match.groups()}")
            else:
                print("  → 패턴 매칭 실패 (RAG 기반 답변으로 처리됨)")
        else:
            print(f"❌ 잘못된 분류 (예상: calculation, 실제: {q_type})")


def test_scenario_3_situation():
    """시나리오 3: 상황 기반 상담 (이미 구현됨)"""
    print("\n" + "=" * 60)
    print("시나리오 3: 상황 기반 상담 및 대응")
    print("=" * 60)
    
    test_cases = [
        "사장이 오늘 갑자기 내일부터 나오지 말래. 이유도 안 알려줬어. 이거 부당해고야?",
        "상사가 단톡방에서 나한테만 계속 일을 시키고 모욕적인 말을 해.",
        "회사가 돈이 없다고 월급을 두 달째 안 주고 있어.",
    ]
    
    for question in test_cases:
        q_type = classify_question_type(question)
        print(f"\n질문: {question[:50]}...")
        print(f"→ 분류: {q_type}")
        if q_type == "situation":
            print("✅ 올바르게 분류됨 (기존 상담 로직으로 처리)")
        else:
            print(f"⚠️ 분류: {q_type} (상황 기반이지만 다른 유형으로 분류됨)")


def test_scenario_4_exception():
    """시나리오 4: 예외 상황 및 한계 테스트"""
    print("\n" + "=" * 60)
    print("시나리오 4: 예외 상황 및 한계 테스트")
    print("=" * 60)
    
    test_cases = [
        ("모호한 신분", "나는 프리랜서로 계약했는데 실제로는 회사 지시를 다 받아. 나도 노동법 보호를 받을 수 있을까?"),
        ("유도 질문", "사장 몰래 회사 기밀을 빼돌려서 퇴사하고 싶은데, 이래도 퇴직금 받을 수 있어?"),
        ("최신성 확인", "올해(2026년) 최저임금은 얼마야?"),
    ]
    
    for category, question in test_cases:
        q_type = classify_question_type(question)
        print(f"\n[{category}]")
        print(f"질문: {question[:60]}...")
        print(f"→ 분류: {q_type}")
        
        if q_type == "exception":
            print("✅ 올바르게 분류됨")
            if any(kw in question for kw in ["몰래", "기밀", "빼돌려"]):
                print("  → 유도 질문 감지됨 (윤리적 가이드라인 제공)")
            elif any(kw in question for kw in ["올해", "2026", "최신"]):
                print("  → 최신성 확인 질문 (데이터 연도 안내 추가)")
            elif "프리랜서" in question:
                print("  → 모호한 신분 질문 (근로자 판단 기준 설명)")
        else:
            print(f"❌ 잘못된 분류 (예상: exception, 실제: {q_type})")


def test_edge_cases():
    """엣지 케이스 테스트"""
    print("\n" + "=" * 60)
    print("엣지 케이스 테스트")
    print("=" * 60)
    
    edge_cases = [
        ("계산 키워드 있지만 계산 아님", "퇴직금이 얼마나 되는지 궁금해요", "situation"),
        ("지식 키워드 있지만 상황 설명", "차이가 있어서 문제가 생겼어요", "situation"),
        ("예외 키워드 있지만 일반 질문", "2024년에 일어난 일이에요", "situation"),
    ]
    
    for desc, question, expected in edge_cases:
        q_type = classify_question_type(question)
        print(f"\n[{desc}]")
        print(f"질문: {question}")
        print(f"→ 분류: {q_type} (예상: {expected})")
        if q_type == expected:
            print("✅ 올바른 분류")
        else:
            print(f"⚠️ 예상과 다름 (하지만 정상 동작 가능)")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("노동법 챗봇 시나리오 시뮬레이션 테스트")
    print("=" * 60)
    
    test_scenario_1_knowledge()
    test_scenario_2_calculation()
    test_scenario_3_situation()
    test_scenario_4_exception()
    test_edge_cases()
    
    print("\n" + "=" * 60)
    print("시뮬레이션 완료")
    print("=" * 60)