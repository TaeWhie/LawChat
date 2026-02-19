# -*- coding: utf-8 -*-
"""LangGraph 기반 노동법 RAG 챗봇 그래프. app.py와 동일한 step1/step2/step3·출력으로 자동 진행 후 말풍선에 표시."""
from typing import TypedDict, Annotated, Literal

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from rag.store import build_vector_store, search
from rag.pipeline import (
    step1_issue_classification,
    step2_checklist,
    step3_conclusion,
    filter_articles_by_issue_relevance,
    _rag_context,
)
from rag.prompts import system_off_topic_detection, user_off_topic_detection
from rag.llm import chat_json, chat
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
from rag.pipeline import _rag_context
from config import (
    ALL_LABOR_LAW_SOURCES,
    RAG_MAIN_TOP_K,
    RAG_FILTER_TOP_K,
)


# 상태 스키마
class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    situation: str
    issues: list[str]
    selected_issue: str
    qa_list: list[dict]
    articles_by_issue: dict
    checklist: list
    checklist_index: int
    phase: str  # "input" | "checklist" | "conclusion"
    pending_question: str  # 사용자 답변 대기 중인 질문
    checklist_rag_results: list  # step2에서 사용한 조문 (2차 시 merge용)


def _get_collection():
    return build_vector_store()[0]


def _detect_intent(last_msg: str, state: ChatbotState) -> Literal["new_situation", "answer_checklist"]:
    """마지막 사용자 메시지가 새 상황인지, checklist 답변인지 판별"""
    phase = state.get("phase", "input")
    if phase == "input" or not state.get("situation"):
        return "new_situation"
    if phase == "checklist" and state.get("checklist"):
        return "answer_checklist"
    if phase == "conclusion":
        return "new_situation"
    return "new_situation"


def process_turn(state: ChatbotState) -> dict:
    """
    사용자 메시지 처리 → 다음 AI 응답 생성
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": [AIMessage(content="상황을 말씀해 주세요. 예: 월급을 못 받았어요")]}
    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        return {}
    user_text = (last_msg.content or "").strip()
    if not user_text:
        return {"messages": [AIMessage(content="메시지를 입력해 주세요.")]}

    col = _get_collection()
    phase = state.get("phase", "input")
    situation = state.get("situation", "")
    issues = list(state.get("issues", []))
    selected_issue = state.get("selected_issue", "")
    qa_list = list(state.get("qa_list", []))
    articles_by_issue = dict(state.get("articles_by_issue", {}))
    checklist = list(state.get("checklist") or [])
    checklist_index = state.get("checklist_index", 0)

    # 새 상황 입력
    if phase == "input" or (not situation and user_text):
        # 노동법과 무관한 질문인지 먼저 확인
        try:
            off_topic_result = chat_json(
                system_off_topic_detection(),
                user_off_topic_detection(user_text),
                max_tokens=50
            )
            is_labor_law_related = True
            if isinstance(off_topic_result, dict):
                is_labor_law_related = off_topic_result.get("is_labor_law_related", True)
            
            if not is_labor_law_related:
                # 노동법과 무관한 질문 → 상담으로 유도
                guidance_msg = """안녕하세요! 저는 **노동법 전문 상담 챗봇**입니다. 

현재 질문은 노동법과 관련이 없는 것으로 보입니다. 저는 다음과 같은 **직장 관련 법적 문제**에 대해 도움을 드릴 수 있습니다:

💼 **상담 가능한 분야**
• 임금·퇴직금 문제 (월급 체불, 퇴직금 미지급 등)
• 해고·징계 문제 (부당해고, 해고 예고 등)
• 근로시간·휴가 문제 (야근, 연차휴가 등)
• 직장 내 괴롭힘·차별
• 산업재해·안전 문제
• 노동조합 관련 문제
• 최저임금·고용보험 등

직장에서 겪고 계신 법적 문제가 있으시면 자세히 말씀해 주세요. 예를 들어:
• "월급을 두 달째 못 받았어요"
• "회사에서 해고 통보를 받았어요"
• "연차휴가를 사용하지 못했어요"

어떤 도움이 필요하신가요?"""
                return {
                    "messages": [AIMessage(content=guidance_msg)],
                    "situation": "",
                    "issues": [],
                    "phase": "input",
                }
        except Exception:
            # 오류 발생 시 기존 로직 계속 진행 (안전장치)
            pass
        
        # 질문 유형 분류 (지식/개념, 계산, 예외, 상황)
        question_type = classify_question_type(user_text)
        
        # 1. 지식 기반 질문 (용어 정의, 개념 설명, 적용 범위 등)
        if question_type == "knowledge":
            try:
                # 관련 조문 검색
                search_results = search(
                    col, user_text, top_k=5,
                    filter_sources=ALL_LABOR_LAW_SOURCES,
                    exclude_sections=["벌칙", "부칙"],
                )
                if search_results:
                    rag_context = _rag_context(search_results, max_length=2000)
                    answer = chat(
                        system_knowledge_qa(),
                        user_knowledge_qa(user_text, rag_context),
                        max_tokens=1000
                    )
                    return {
                        "messages": [AIMessage(content=answer)],
                        "situation": "",
                        "issues": [],
                        "selected_issue": "",
                        "qa_list": [],
                        "articles_by_issue": {},
                        "checklist": [],
                        "checklist_index": 0,
                        "phase": "input",
                        "pending_question": "",
                        "checklist_rag_results": [],
                    }
            except Exception:
                # 지식 질문인데 오류 발생 → 체크리스트 없이 바로 답변만 반환
                return {
                    "messages": [AIMessage(content="질문 처리 중 오류가 발생했습니다. 다시 질문해 주세요.")],
                    "situation": "",
                    "issues": [],
                    "phase": "input",
                }
        
        # 2. 계산 질문 (퇴직금, 연장근로 수당 등)
        elif question_type == "calculation":
            try:
                import re
                from datetime import datetime
                
                # 퇴직금 계산 패턴 (더 유연하게 - 한글 처리)
                severance_patterns = [
                    # "2022년 1월 1일 입사 ... 2024년 2월 28일 퇴사 ... 300만 원"
                    r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?(\d+)[만천백]?\s*원",
                    # "입사 ... 퇴사 ... 월급 ... 만원"
                    r"입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?퇴사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?월급.*?(\d+)[만천백]?\s*원",
                    # "2022-01-01 입사 ... 2024-02-28 퇴사 ... 300만원"
                    r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2}).*?입사.*?(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2}).*?퇴사.*?(\d+)[만천백]?\s*원",
                ]
                severance_match = None
                for pattern in severance_patterns:
                    severance_match = re.search(pattern, user_text, re.IGNORECASE | re.DOTALL)
                    if severance_match:
                        break
                
                # 연장근로 수당 계산 패턴 (더 유연하게)
                # "8시간 근무하고 2시간 더" 또는 "8시간 2시간 만원" 등 다양한 패턴
                overtime_patterns = [
                    r"(\d+)시간.*?(\d+)시간.*?(\d+)[만천백]?\s*원",  # "8시간 2시간 만원"
                    r"(\d+)시간.*?근무.*?(\d+)시간.*?(\d+)[만천백]?\s*원",  # "8시간 근무 2시간 만원"
                    r"(\d+)시간.*?(\d+)시간.*?시급.*?(\d+)[만천백]?\s*원",  # "8시간 2시간 시급 만원"
                ]
                overtime_match = None
                for pattern in overtime_patterns:
                    overtime_match = re.search(pattern, user_text, re.IGNORECASE)
                    if overtime_match:
                        break
                
                if severance_match:
                    start_date = f"{severance_match.group(1)}-{severance_match.group(2).zfill(2)}-{severance_match.group(3).zfill(2)}"
                    end_date = f"{severance_match.group(4)}-{severance_match.group(5).zfill(2)}-{severance_match.group(6).zfill(2)}"
                    monthly_salary = float(severance_match.group(7)) * 10000  # 만원 단위 변환
                    calc_result = calculate_severance_pay(start_date, end_date, monthly_salary)
                    if calc_result.get("success"):
                        answer = f"""**퇴직금 계산 결과** (근로기준법 제34조 기준)

📅 근무 기간: {calc_result['work_days']}일 ({calc_result['work_years']}년)
💰 월 평균임금: {calc_result['monthly_salary']:,.0f}원
📊 계산식: {calc_result['formula']}

**예상 퇴직금: 약 {calc_result['estimated_severance']:,}원**

⚠️ {calc_result['note']}
정확한 계산을 위해서는 최근 3개월간의 임금 총액과 각종 수당을 포함한 평균임금이 필요합니다."""
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
                
                elif overtime_match:
                    base_hours = int(overtime_match.group(1))
                    overtime_hours = int(overtime_match.group(2))
                    hourly_wage = int(overtime_match.group(3)) * 10000  # 만원 단위 변환
                    calc_result = calculate_overtime_pay(base_hours, overtime_hours, hourly_wage)
                    if calc_result.get("success"):
                        answer = f"""**연장근로 수당 계산 결과** (근로기준법 제56조 기준)

⏰ 기본 근무: {calc_result['base_hours']}시간 → {calc_result['base_pay']:,}원
🌙 연장 근무: {calc_result['overtime_hours']}시간 → {calc_result['overtime_pay']:,}원 (시급의 150%)

**총 수당: {calc_result['total_pay']:,}원**

📋 계산식: {calc_result['formula']}

💡 {calc_result['note']}"""
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
                else:
                    # 계산 질문이지만 패턴 매칭 실패 → RAG로 답변
                    search_results = search(
                        col, user_text, top_k=5,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                    )
                    if search_results:
                        rag_context = _rag_context(search_results, max_length=2000)
                        answer = chat(
                            system_calculation_qa(),
                            user_calculation_qa(user_text, rag_context),
                            max_tokens=1000
                        )
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
            except Exception as e:
                # 계산 질문인데 오류 발생 → 체크리스트 없이 바로 답변만 반환
                return {
                    "messages": [AIMessage(content="계산 질문 처리 중 오류가 발생했습니다. 질문을 다시 정확히 입력해 주세요.")],
                    "situation": "",
                    "issues": [],
                    "phase": "input",
                }
        
        # 3. 예외 상황 질문 (모호한 신분, 유도 질문, 최신성 확인)
        elif question_type == "exception":
            try:
                # 유도 질문 감지 (최우선)
                if any(kw in user_text for kw in ["몰래", "기밀", "빼돌려"]):
                    # 유도 질문에 대해 RAG 검색으로 관련 노동법 조문 찾기
                    search_query = "해고 사유 정당한 해고 퇴직금 계약 위반 근로계약"
                    search_results = search(
                        col, search_query, top_k=5,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    
                    # RAG 기반 답변 생성
                    answer = chat(
                        system_exception_qa(),
                        user_exception_qa(user_text, rag_context),
                        max_tokens=None  # reasoning 모델이 충분히 답변하도록 제한 없음
                    )
                    
                    # RAG 검색 결과가 없거나 답변이 부족한 경우 기본 가이드라인 추가
                    if not rag_context or len(answer.strip()) < 100:
                        answer = """⚠️ **법적·윤리적 가이드라인**

회사 기밀을 유출하거나 불법적인 행위를 하는 것은 법적으로 금지되어 있으며, 형사처벌을 받을 수 있습니다.

**법적 문제:**
- 업무상 배임죄 (형법 제356조)
- 영업비밀 침해 (부정경쟁방지법)
- 계약 위반으로 인한 손해배상

**퇴직금과의 관계:**
불법 행위로 인한 해고는 정당한 해고 사유가 될 수 있으며, 퇴직금 지급에도 영향을 줄 수 있습니다.

**올바른 방법:**
- 정당한 절차를 통해 퇴사
- 노동위원회나 법률 상담을 통한 권리 구제
- 필요시 변호사 상담

법적 문제가 있으시면 변호사와 상담하시기 바랍니다."""
                else:
                    # 프리랜서 관련 질문은 적절한 검색어 사용
                    search_query = user_text
                    if "프리랜서" in user_text or "프리" in user_text:
                        # 근로자 판단 기준 관련 조문 검색
                        search_query = "근로자 판단 기준 근로계약 용역계약 위장도급"
                    elif any(kw in user_text for kw in ["올해", "2026", "2025", "2024", "최신"]):
                        # 최신성 확인 질문: 원래 질문 그대로 검색 (최저임금 등)
                        search_query = user_text
                    
                    search_results = search(
                        col, search_query, top_k=5,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    
                    answer = chat(
                        system_exception_qa(),
                        user_exception_qa(user_text, rag_context),
                        max_tokens=None  # reasoning 모델이 충분히 답변하도록 제한 없음
                    )
                    
                    # 최신성 확인 질문인 경우 데이터 연도 추가
                    if any(kw in user_text for kw in ["올해", "2026", "2025", "2024", "최신"]):
                        answer += "\n\n📅 **데이터 참고사항:** 제공된 법령 데이터는 동기화 시점의 법령을 기준으로 합니다. 법령은 개정될 수 있으므로, 최신 법령 확인이 필요하시면 국가법령정보센터(www.law.go.kr)를 참고하시기 바랍니다."
                
                return {
                    "messages": [AIMessage(content=answer)],
                    "situation": "",
                    "issues": [],
                    "selected_issue": "",
                    "qa_list": [],
                    "articles_by_issue": {},
                    "checklist": [],
                    "checklist_index": 0,
                    "phase": "input",
                    "pending_question": "",
                    "checklist_rag_results": [],
                }
            except Exception as e:
                # 예외 질문인데 오류 발생 → 에러 메시지 (체크리스트 없이)
                return {
                    "messages": [AIMessage(content="질문 처리 중 오류가 발생했습니다. 다시 질문해 주세요.")],
                    "situation": "",
                    "issues": [],
                    "selected_issue": "",
                    "qa_list": [],
                    "articles_by_issue": {},
                    "checklist": [],
                    "checklist_index": 0,
                    "phase": "input",
                    "pending_question": "",
                    "checklist_rag_results": [],
                }
        
        # 4. 상황 기반 상담만 체크리스트 생성 (question_type == "situation"일 때만)
        # 지식/계산/예외 질문은 위에서 모두 return했으므로 여기 도달하지 않음
        situation = user_text
        issues, step1_articles, _ = step1_issue_classification(situation, collection=col)
        if not issues:
            return {
                "messages": [AIMessage(content="제공된 법령 데이터에서 해당 상황에 맞는 이슈를 찾지 못했습니다.\n\n직장에서 겪고 계신 구체적인 문제를 말씀해 주시면 더 정확한 상담을 도와드릴 수 있습니다. 예: '월급을 못 받았어요', '해고당했어요', '연차휴가를 사용하지 못했어요'")],
                "situation": situation,
                "issues": [],
                "phase": "input",
            }
        selected_issue = issues[0]
        # step1에서 반환한 이슈별 조문 사용. 비어 있으면 app.py와 동일하게 ALL_LABOR_LAW_SOURCES로 보충
        articles_by_issue = dict(step1_articles) if step1_articles else {}
        for issue_item in issues:
            if issue_item in articles_by_issue and articles_by_issue[issue_item]:
                continue
            seen = set()
            issue_articles = []
            for q in [issue_item, situation]:
                if not (q or str(q).strip()):
                    continue
                res = search(
                    col, q, top_k=RAG_MAIN_TOP_K,
                    filter_sources=ALL_LABOR_LAW_SOURCES,
                    exclude_sections=["벌칙", "부칙"],
                    exclude_chapters=["제1장 총칙"],
                )
                for r in res:
                    art = r.get("article", "")
                    if art and art not in seen:
                        issue_articles.append(r)
                        seen.add(art)
            articles_by_issue[issue_item] = filter_articles_by_issue_relevance(
                issue_item, issue_articles, top_k=RAG_FILTER_TOP_K
            )
        qa_list = []
        # 이슈 선택 후 바로 체크리스트 (app.py와 동일: filter_preview 400자, remaining_articles)
        remaining = articles_by_issue.get(selected_issue) or []
        filter_preview = (selected_issue + " " + "\n".join(f"Q: {x['question']} A: {x['answer']}" for x in qa_list))[:400]
        step2_res = step2_checklist(
            selected_issue, filter_preview, collection=col,
            narrow_answers=None,
            qa_list=qa_list,
            remaining_articles=remaining,
        )
        checklist = step2_res.get("checklist", []) if isinstance(step2_res, dict) else (step2_res or [])
        if checklist:
            # 말풍선에는 안내만. 질문 전문은 앱 아래 '체크리스트 답변' 영역에만 표시
            resp = f"감지된 이슈: {', '.join(issues)}\n\n체크리스트가 생성되었습니다. 아래에서 각 질문에 대해 **네** / **아니요** / **모르겠음** 버튼을 눌러 주세요."
            return {
                "messages": [AIMessage(content=resp)],
                "situation": situation, "issues": issues, "selected_issue": selected_issue,
                "qa_list": qa_list, "articles_by_issue": articles_by_issue,
                "checklist": checklist, "checklist_index": 0,
                "phase": "checklist", "pending_question": "",
                "checklist_rag_results": step2_res.get("rag_results", []) if isinstance(step2_res, dict) else [],
            }
        narrow_answers = [x.get("answer", "").strip() for x in qa_list if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
        res = step3_conclusion(selected_issue, qa_list, collection=col, narrow_answers=narrow_answers if narrow_answers else None)
        conc = res.get("conclusion", res) if isinstance(res, dict) else str(res)
        rel = res.get("related_articles", []) if isinstance(res, dict) else []
        tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
        return {
            "messages": [AIMessage(content=f"감지된 이슈: {', '.join(issues)}\n\n**결론**\n\n{conc}{tail}")],
            "situation": situation, "issues": issues, "selected_issue": selected_issue,
            "qa_list": qa_list, "phase": "conclusion", "pending_question": "",
        }

    # checklist 답변은 앱에서 버튼(네/아니요/모르겠음)으로 수집 후 step3/step2 호출하므로 그래프에서는 처리하지 않음
    
    # 체크리스트 단계에서 새로운 텍스트 입력이 들어온 경우 → 새 상담으로 처리
    # (phase == "checklist"이고 버튼이 아닌 텍스트 입력)
    if phase == "checklist":
        # 노동법과 무관한 질문인지 먼저 확인
        try:
            off_topic_result = chat_json(
                system_off_topic_detection(),
                user_off_topic_detection(user_text),
                max_tokens=50
            )
            is_labor_law_related = True
            if isinstance(off_topic_result, dict):
                is_labor_law_related = off_topic_result.get("is_labor_law_related", True)
            
            if not is_labor_law_related:
                # 노동법과 무관한 질문 → 상담으로 유도
                guidance_msg = """안녕하세요! 저는 **노동법 전문 상담 챗봇**입니다. 

현재 질문은 노동법과 관련이 없는 것으로 보입니다. 저는 다음과 같은 **직장 관련 법적 문제**에 대해 도움을 드릴 수 있습니다:

💼 **상담 가능한 분야**
• 임금·퇴직금 문제 (월급 체불, 퇴직금 미지급 등)
• 해고·징계 문제 (부당해고, 해고 예고 등)
• 근로시간·휴가 문제 (야근, 연차휴가 등)
• 직장 내 괴롭힘·차별
• 산업재해·안전 문제
• 노동조합 관련 문제
• 최저임금·고용보험 등

직장에서 겪고 계신 법적 문제가 있으시면 자세히 말씀해 주세요. 예를 들어:
• "월급을 두 달째 못 받았어요"
• "회사에서 해고 통보를 받았어요"
• "연차휴가를 사용하지 못했어요"

어떤 도움이 필요하신가요?"""
                return {
                    "messages": [AIMessage(content=guidance_msg)],
                    "situation": "",
                    "issues": [],
                    "phase": "input",
                }
        except Exception:
            # 오류 발생 시 기존 로직 계속 진행 (안전장치)
            pass
        
        # 노동법 관련 질문이면 새 상담으로 시작 (기존 체크리스트는 무시)
        # 질문 유형에 따라 적절히 처리 (지식/계산/예외/상황)
        question_type = classify_question_type(user_text)
        
        # 지식/계산/예외 질문은 바로 답변 (체크리스트 없이)
        if question_type == "knowledge":
            try:
                search_results = search(
                    col, user_text, top_k=5,
                    filter_sources=ALL_LABOR_LAW_SOURCES,
                    exclude_sections=["벌칙", "부칙"],
                )
                if search_results:
                    rag_context = _rag_context(search_results, max_length=2000)
                    answer = chat(
                        system_knowledge_qa(),
                        user_knowledge_qa(user_text, rag_context),
                        max_tokens=1000
                    )
                    return {
                        "messages": [AIMessage(content=answer)],
                        "situation": "",
                        "issues": [],
                        "selected_issue": "",
                        "qa_list": [],
                        "articles_by_issue": {},
                        "checklist": [],
                        "checklist_index": 0,
                        "phase": "input",
                        "pending_question": "",
                        "checklist_rag_results": [],
                    }
            except Exception:
                pass
        
        elif question_type == "calculation":
            try:
                import re
                severance_patterns = [
                    r"(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일]?\s*퇴사.*?(\d+)[만천백]?\s*원",
                    r"입사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?퇴사.*?(\d{4})[년.\-/]?\s*(\d{1,2})[월.\-/]?\s*(\d{1,2})[일].*?월급.*?(\d+)[만천백]?\s*원",
                    r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2}).*?입사.*?(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2}).*?퇴사.*?(\d+)[만천백]?\s*원",
                ]
                severance_match = None
                for pattern in severance_patterns:
                    severance_match = re.search(pattern, user_text, re.IGNORECASE | re.DOTALL)
                    if severance_match:
                        break
                
                overtime_patterns = [
                    r"(\d+)시간.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
                    r"(\d+)시간.*?근무.*?(\d+)시간.*?(\d+)[만천백]?\s*원",
                    r"(\d+)시간.*?(\d+)시간.*?시급.*?(\d+)[만천백]?\s*원",
                ]
                overtime_match = None
                for pattern in overtime_patterns:
                    overtime_match = re.search(pattern, user_text, re.IGNORECASE)
                    if overtime_match:
                        break
                
                if severance_match:
                    start_date = f"{severance_match.group(1)}-{severance_match.group(2).zfill(2)}-{severance_match.group(3).zfill(2)}"
                    end_date = f"{severance_match.group(4)}-{severance_match.group(5).zfill(2)}-{severance_match.group(6).zfill(2)}"
                    monthly_salary = float(severance_match.group(7)) * 10000
                    calc_result = calculate_severance_pay(start_date, end_date, monthly_salary)
                    if calc_result.get("success"):
                        answer = f"""**퇴직금 계산 결과** (근로기준법 제34조 기준)

📅 근무 기간: {calc_result['work_days']}일 ({calc_result['work_years']}년)
💰 월 평균임금: {calc_result['monthly_salary']:,.0f}원
📊 계산식: {calc_result['formula']}

**예상 퇴직금: 약 {calc_result['estimated_severance']:,}원**

⚠️ {calc_result['note']}
정확한 계산을 위해서는 최근 3개월간의 임금 총액과 각종 수당을 포함한 평균임금이 필요합니다."""
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
                
                elif overtime_match:
                    base_hours = int(overtime_match.group(1))
                    overtime_hours = int(overtime_match.group(2))
                    hourly_wage = int(overtime_match.group(3)) * 10000
                    calc_result = calculate_overtime_pay(base_hours, overtime_hours, hourly_wage)
                    if calc_result.get("success"):
                        answer = f"""**연장근로 수당 계산 결과** (근로기준법 제56조 기준)

⏰ 기본 근무: {calc_result['base_hours']}시간 → {calc_result['base_pay']:,}원
🌙 연장 근무: {calc_result['overtime_hours']}시간 → {calc_result['overtime_pay']:,}원 (시급의 150%)

**총 수당: {calc_result['total_pay']:,}원**

📋 계산식: {calc_result['formula']}

💡 {calc_result['note']}"""
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
                else:
                    search_results = search(
                        col, user_text, top_k=5,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                    )
                    if search_results:
                        rag_context = _rag_context(search_results, max_length=2000)
                        answer = chat(
                            system_calculation_qa(),
                            user_calculation_qa(user_text, rag_context),
                            max_tokens=1000
                        )
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
            except Exception:
                pass
        
        elif question_type == "exception":
            try:
                if any(kw in user_text for kw in ["몰래", "기밀", "빼돌려"]):
                    search_query = "해고 사유 정당한 해고 퇴직금 계약 위반 근로계약"
                    search_results = search(
                        col, search_query, top_k=5,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    answer = chat(
                        system_exception_qa(),
                        user_exception_qa(user_text, rag_context),
                        max_tokens=None
                    )
                    if not rag_context or len(answer.strip()) < 100:
                        answer = """⚠️ **법적·윤리적 가이드라인**

회사 기밀을 유출하거나 불법적인 행위를 하는 것은 법적으로 금지되어 있으며, 형사처벌을 받을 수 있습니다.

**법적 문제:**
- 업무상 배임죄 (형법 제356조)
- 영업비밀 침해 (부정경쟁방지법)
- 계약 위반으로 인한 손해배상

**퇴직금과의 관계:**
불법 행위로 인한 해고는 정당한 해고 사유가 될 수 있으며, 퇴직금 지급에도 영향을 줄 수 있습니다.

**올바른 방법:**
- 정당한 절차를 통해 퇴사
- 노동위원회나 법률 상담을 통한 권리 구제
- 필요시 변호사 상담

법적 문제가 있으시면 변호사와 상담하시기 바랍니다."""
                else:
                    search_query = user_text
                    if "프리랜서" in user_text or "프리" in user_text:
                        search_query = "근로자 판단 기준 근로계약 용역계약 위장도급"
                    elif any(kw in user_text for kw in ["올해", "2026", "2025", "2024", "최신"]):
                        search_query = user_text
                    
                    search_results = search(
                        col, search_query, top_k=5,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    answer = chat(
                        system_exception_qa(),
                        user_exception_qa(user_text, rag_context),
                        max_tokens=None
                    )
                    if any(kw in user_text for kw in ["올해", "2026", "2025", "2024", "최신"]):
                        answer += "\n\n📅 **데이터 참고사항:** 제공된 법령 데이터는 동기화 시점의 법령을 기준으로 합니다. 법령은 개정될 수 있으므로, 최신 법령 확인이 필요하시면 국가법령정보센터(www.law.go.kr)를 참고하시기 바랍니다."
                
                return {
                    "messages": [AIMessage(content=answer)],
                    "situation": "",
                    "issues": [],
                    "selected_issue": "",
                    "qa_list": [],
                    "articles_by_issue": {},
                    "checklist": [],
                    "checklist_index": 0,
                    "phase": "input",
                    "pending_question": "",
                    "checklist_rag_results": [],
                }
            except Exception:
                pass
        
        # 상황 기반 질문이면 새 상담 시작 (기존 체크리스트 무시하고 새로 시작)
        # 라인 96의 조건으로 다시 들어가서 처리됨
        # 하지만 phase가 "checklist"이므로 라인 96 조건이 False가 되어 여기 도달함
        # 따라서 새 상담 시작 메시지 반환
        return {
            "messages": [AIMessage(content="새로운 상황을 말씀해 주세요. 예: 퇴직금을 못 받았어요")],
            "situation": "", "issues": [], "selected_issue": "", "qa_list": [],
            "articles_by_issue": {}, "checklist": [], "checklist_index": 0,
            "phase": "input", "pending_question": "", "checklist_rag_results": [],
        }

    # 새 상담 시작 (phase가 "conclusion"이거나 기타 경우)
    return {
        "messages": [AIMessage(content="새로운 상황을 말씀해 주세요. 예: 퇴직금을 못 받았어요")],
        "situation": "", "issues": [], "selected_issue": "", "qa_list": [],
        "articles_by_issue": {}, "checklist": [], "checklist_index": 0,
        "phase": "input", "pending_question": "", "checklist_rag_results": [],
    }


def build_graph():
    """LangGraph 빌드 및 컴파일"""
    builder = StateGraph(ChatbotState)
    builder.add_node("process", process_turn)
    builder.add_edge(START, "process")
    builder.add_edge("process", END)
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


def get_graph():
    """그래프 인스턴스 (캐시)"""
    if not hasattr(get_graph, "_graph"):
        get_graph._graph = build_graph()
    return get_graph._graph
