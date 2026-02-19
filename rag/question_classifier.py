# -*- coding: utf-8 -*-
"""질문 유형 분류 및 처리 모듈"""

import re
from typing import Dict, Any, Optional, Literal
from rag.store import build_vector_store, search
from rag.llm import chat, chat_json
from rag.prompts import RAG_ONLY_RULE
from config import ALL_LABOR_LAW_SOURCES


def classify_question_type(user_text: str) -> Literal["knowledge", "calculation", "situation", "exception"]:
    """질문 유형 분류: knowledge(지식/개념), calculation(계산), situation(상황), exception(예외)"""
    text = user_text.lower()
    
    # 예외 상황 키워드 (최우선 체크 - 유도 질문, 모호한 신분, 최신성 확인)
    # 단, 날짜가 포함된 계산 질문은 제외
    exception_keywords_strict = ["프리랜서", "몰래", "기밀", "빼돌려"]
    exception_keywords_date = ["올해", "2026", "2025", "2024", "최신"]
    
    # 엄격한 예외 키워드 (프리랜서, 불법 행위 등)
    if any(kw in text for kw in exception_keywords_strict):
        return "exception"
    
    # 날짜 관련 예외 키워드는 계산 질문이 아닐 때만
    if any(kw in text for kw in exception_keywords_date):
        # 계산 질문이 아니면 예외로 처리
        is_calc_question = any(kw in text for kw in ["얼마", "계산", "대략", "총", "받아야", "받을 수 있어", "받을 수 있"]) and \
                          any(kw in text for kw in ["퇴직금", "수당", "급여", "임금", "연장", "야근", "최저임금"])
        if not is_calc_question:
            return "exception"
    
    # 계산 질문 키워드
    calc_keywords = ["얼마", "계산", "대략", "총", "받아야", "받을 수 있어", "받을 수 있", "기간", "일 동안", "원이면"]
    calc_context = ["퇴직금", "수당", "급여", "임금", "연장", "야근", "근무", "일했어", "실업급여"]
    
    # 계산 질문: 계산 키워드 + 계산 맥락 또는 숫자 패턴
    has_calc_keyword = any(kw in text for kw in calc_keywords)
    has_calc_context = any(kw in text for kw in calc_context)
    has_number_pattern = bool(re.search(r"\d+[만천백]?\s*원", text) or re.search(r"\d+시간.*\d+시간", text) or 
                             re.search(r"\d{4}.*입사.*\d{4}.*퇴사", text))
    
    if has_calc_keyword and (has_calc_context or has_number_pattern):
        return "calculation"
    
    # 지식/개념 질문 키워드 (계산보다 우선)
    knowledge_keywords = ["차이", "뭐야", "무엇", "의미", "정의", "개념", "적용", "받을 수 있어", "우선순위", "어떻게 돼", "뭐예요"]
    # "받을 수 있어"는 맥락에 따라 다르므로, 계산 맥락이 없을 때만 지식 질문
    if "받을 수 있어" in text or "받을 수 있" in text:
        if not has_calc_context:
            return "knowledge"
    elif any(kw in text for kw in knowledge_keywords):
        return "knowledge"
    
    # 기본값: 상황 기반 상담
    return "situation"


def system_knowledge_qa():
    """지식 기반 질문 답변 시스템 프롬프트"""
    return (
        "You are a Korean labor law expert answering knowledge-based questions about legal terms, concepts, and scope of application. "
        + RAG_ONLY_RULE
        + """
Your task: Answer questions about legal definitions, differences between terms, scope of application, and legal precedence.

**Rules:**
- Use ONLY the provided legal provisions. Do not use general knowledge.
- Explain in simple, everyday Korean that non-lawyers can understand.
- Always cite the specific article number (e.g., 근로기준법 제36조).
- If the question asks about differences, clearly compare both terms.
- If the question asks about scope (e.g., "5인 미만 사업장"), explain who is covered and who is not.
- If the question asks about legal precedence, explain which law takes priority.

**Output format:**
- Start with a brief answer
- Then provide detailed explanation with article citations
- Use examples when helpful

Write your answer in Korean.
"""
    )


def user_knowledge_qa(question: str, rag_context: str) -> str:
    """지식 기반 질문 답변용 사용자 프롬프트"""
    return f"""Question: {question}

[Provided legal provisions]
{rag_context}

Answer the question based ONLY on the provisions above. Explain in simple Korean."""


def calculate_severance_pay(start_date: str, end_date: str, monthly_salary: float) -> Dict[str, Any]:
    """퇴직금 계산 (근로기준법 제34조)"""
    from datetime import datetime
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end - start).days + 1
        years = days / 365.0
        
        # 평균임금 = 최근 3개월 임금 총액 / 3개월 일수
        # 간단 계산: 월급을 평균임금으로 가정
        avg_daily = monthly_salary / 30
        severance = avg_daily * 30 * years
        
        return {
            "success": True,
            "work_days": days,
            "work_years": round(years, 2),
            "monthly_salary": monthly_salary,
            "estimated_severance": round(severance),
            "formula": f"평균임금 × 30일 × 근속연수 = {round(monthly_salary/30)}원 × 30일 × {round(years, 2)}년",
            "note": "정확한 계산을 위해서는 최근 3개월간의 임금 총액이 필요합니다."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def calculate_overtime_pay(base_hours: int, overtime_hours: int, hourly_wage: int) -> Dict[str, Any]:
    """연장근로 수당 계산 (근로기준법 제56조)"""
    try:
        # 기본 8시간 근무
        base_pay = base_hours * hourly_wage
        
        # 연장근로: 8시간 초과 시 시급의 50% 가산
        if overtime_hours > 0:
            overtime_pay = overtime_hours * hourly_wage * 1.5
        else:
            overtime_pay = 0
        
        total = base_pay + overtime_pay
        
        return {
            "success": True,
            "base_hours": base_hours,
            "base_pay": base_pay,
            "overtime_hours": overtime_hours,
            "overtime_pay": round(overtime_pay),
            "total_pay": round(total),
            "formula": f"기본임금({base_hours}시간 × {hourly_wage}원) + 연장근로수당({overtime_hours}시간 × {hourly_wage}원 × 1.5배)",
            "note": "근로기준법 제56조에 따라 8시간 초과 근로 시 시급의 50%를 가산하여 지급해야 합니다."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def system_calculation_qa():
    """계산 질문 답변 시스템 프롬프트"""
    return (
        "You are a Korean labor law expert helping users calculate severance pay, overtime pay, and other labor-related amounts. "
        + RAG_ONLY_RULE
        + """
Your task: Extract information from the user's question and provide calculations based on Korean labor law.

**Calculation types:**
1. Severance pay (퇴직금): 평균임금 × 30일 × 근속연수
2. Overtime pay (연장근로수당): 초과시간 × 시급 × 1.5배
3. Unemployment benefits (실업급여): 고용보험 가입기간과 나이에 따라 결정

**Rules:**
- Extract dates, amounts, hours from the question
- Use the provided legal provisions to confirm calculation formulas
- Show the calculation step by step
- Always cite the relevant article (e.g., 근로기준법 제34조, 제56조)
- If information is missing, ask for it clearly

Write your answer in Korean with clear calculations.
"""
    )


def user_calculation_qa(question: str, rag_context: str) -> str:
    """계산 질문 답변용 사용자 프롬프트"""
    return f"""Question: {question}

[Provided legal provisions]
{rag_context}

Extract the necessary information (dates, amounts, hours) from the question and calculate based on the provisions above. Show step-by-step calculation."""


def system_exception_qa():
    """예외 상황 질문 답변 시스템 프롬프트"""
    return (
        "You are a Korean labor law expert handling edge cases and boundary questions. "
        + RAG_ONLY_RULE
        + """
Your task: Answer questions about ambiguous employment status, ethical guidance, and data currency.

**Types of questions:**
1. Ambiguous status (프리랜서 vs 근로자): Determine if someone qualifies as a worker under labor law
2. Ethical questions: Provide guidance on legal and ethical boundaries
3. Data currency: Confirm if information is current (mention data source year if known)

**Rules:**
- For ambiguous status: Explain the criteria for being considered a "worker" (근로자)
- For ethical questions: Clearly state what is legal vs illegal, and provide ethical guidance
- For data currency: Mention the effective year of the legal provisions, and note that laws may change
- Always cite relevant articles
- If uncertain, recommend consulting with a labor attorney

Write your answer in Korean.
"""
    )


def user_exception_qa(question: str, rag_context: str) -> str:
    """예외 상황 질문 답변용 사용자 프롬프트"""
    return f"""Question: {question}

[Provided legal provisions]
{rag_context}

Answer this edge case or exception question based on the provisions above. Provide clear guidance."""