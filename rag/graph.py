# -*- coding: utf-8 -*-
"""LangGraph 기반 노동법 RAG 챗봇 그래프. app.py와 동일한 step1/step2/step3·출력으로 자동 진행 후 말풍선에 표시."""
from typing import TypedDict, Annotated, Literal, Optional, Dict, Any

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
    step1_and_step2_parallel,
)
from rag.prompts import system_off_topic_detection, user_off_topic_detection
from rag.llm import chat_json, chat, chat_stream, chat_with_metadata
from rag.labor_keywords import is_labor_law_related_fast
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
    pending_question: str
    checklist_rag_results: list
    prompt_overrides: Optional[Dict[str, str]]  # API 요청 시 커스텀 프롬프트 (선택)
    response_format: Optional[str]  # "markdown" | "plain"
    max_length: Optional[int]  # 응답 최대 문자 수
    language: Optional[str]  # "ko" | "en"
    tone: Optional[str]  # "formal" | "casual"
    top_k: Optional[int]  # 이슈 분류·검색 조문 수
    filter_sources: Optional[list]  # 검색 대상 법령 목록
    usage: Optional[Dict[str, int]]  # 토큰 사용량 누적 (prompt_tokens, completion_tokens, total_tokens)


def _merge_usage(prev: Optional[Dict], new: Optional[Dict]) -> Dict[str, int]:
    """두 usage 딕셔너리를 합산. API 응답용."""
    p = prev or {}
    n = new or {}
    return {
        "prompt_tokens": (p.get("prompt_tokens") or 0) + (n.get("prompt_tokens") or 0),
        "completion_tokens": (p.get("completion_tokens") or 0) + (n.get("completion_tokens") or 0),
        "total_tokens": (p.get("total_tokens") or 0) + (n.get("total_tokens") or 0),
    }


# 벡터스토어 컬렉션 캐싱 (프로세스 내 최초 1회만 build_vector_store 호출)
_collection_cache = None

def _get_collection():
    global _collection_cache
    if _collection_cache is None:
        _collection_cache = build_vector_store()[0]
    return _collection_cache


def _knowledge_empty_fallback(user_text: str, rag_context: str) -> str:
    """LLM이 빈 답을 줬을 때 RAG 조문만으로 재요청. 그래도 없으면 검색된 조문 본문을 그대로 반환."""
    retry_sys = (
        "You are a Korean labor law expert. Answer the user's question using ONLY the following legal text. "
        "Write 2-4 short paragraphs in Korean. Do not add anything not in the text. "
        "Do not say you cannot answer if the text contains relevant information. Cite article numbers from the text."
    )
    retry_user = f"Question: {user_text}\n\n[Legal text]\n{rag_context}\n\nAnswer based ONLY on the legal text above, in Korean."
    try:
        answer_retry = chat(retry_sys, retry_user, max_tokens=1000)
        if answer_retry and str(answer_retry).strip():
            return answer_retry
    except Exception:
        pass
    # 조문 그대로 노출 (RAG에서 불러온 내용)
    max_len = 3200
    if len(rag_context) > max_len:
        shown = rag_context[:max_len] + "\n\n...(이하 생략)"
    else:
        shown = rag_context
    return "**검색된 조문**\n\n" + shown + "\n\n위 조문을 참고해 주세요. 퇴직금·연장근로 수당 등 **금액 계산**이 필요하시면 입사일, 퇴사일, 월급(또는 시급·근무시간)을 적어 주시면 계산해 드립니다."


def _calculation_empty_fallback(user_text: str, rag_context: str) -> str:
    """계산 질문인데 LLM이 빈 답을 줬을 때 RAG 조문만으로 재요청. 그래도 없으면 검색된 조문 본문 그대로 반환."""
    retry_sys = (
        "You are a Korean labor law expert. Answer the user's question about calculation (severance pay, overtime pay, etc.) "
        "using ONLY the following legal text. Explain the formula and conditions from the text in 2-4 short paragraphs in Korean. "
        "Do not add anything not in the text. Cite article numbers from the text."
    )
    retry_user = f"Question: {user_text}\n\n[Legal text]\n{rag_context}\n\nAnswer based ONLY on the legal text above, in Korean. If the user needs a specific amount calculated, tell them to provide dates and salary."
    try:
        answer_retry = chat(retry_sys, retry_user, max_tokens=1000)
        if answer_retry and str(answer_retry).strip():
            return answer_retry
    except Exception:
        pass
    max_len = 3200
    if len(rag_context) > max_len:
        shown = rag_context[:max_len] + "\n\n...(이하 생략)"
    else:
        shown = rag_context
    return "**검색된 조문**\n\n" + shown + "\n\n위 조문을 참고해 주세요. 구체적인 **금액**을 계산해 드리려면 입사일, 퇴사일, 월급(또는 시급·근무시간)을 적어 주시면 계산해 드립니다."


def _prepend_rag_for_calculation(col, user_text: str, calc_result_section: str, query: str, filter_sources=None):
    """계산 결과 앞에 RAG에서 가져온 해당 조문을 붙여 반환. 관련 조항이 없으면 폴백 검색."""
    fs = filter_sources if (filter_sources and isinstance(filter_sources, list)) else ALL_LABOR_LAW_SOURCES
    fallback_queries = {
        "퇴직금": ["퇴직금 평균임금 재직일수 제34조", "퇴직금 지급 근로기준법", "퇴직금"],
        "연장근로": ["연장근로 수당 가산 제56조", "연장근로 가산근로기준법", "연장근로 수당"],
    }
    queries_to_try = [query]
    if "퇴직금" in query or "제34조" in query:
        queries_to_try.extend(fallback_queries["퇴직금"])
    if "연장" in query or "제56조" in query:
        queries_to_try.extend(fallback_queries["연장근로"])
    # 중복 제거, 순서 유지
    seen = set()
    for q in queries_to_try:
        if q not in seen:
            seen.add(q)
            try:
                search_results = search(
                    col, q, top_k=3,
                    filter_sources=fs,
                    exclude_sections=["벌칙", "부칙"],
                )
                if search_results:
                    rag_context = _rag_context(search_results, max_length=1200)
                    return "**검색된 조문**\n\n" + rag_context + "\n\n**계산 결과**\n\n" + calc_result_section
            except Exception:
                pass
    return "**계산 결과**\n\n" + calc_result_section


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
    _u = state.get("usage")
    accumulated_usage = dict(_u) if _u else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if not messages:
        return {"messages": [AIMessage(content="상황을 말씀해 주세요. 예: 월급을 못 받았어요")], "usage": accumulated_usage}
    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        return {}
    user_text = (last_msg.content or "").strip()
    if not user_text:
        return {"messages": [AIMessage(content="메시지를 입력해 주세요.")], "usage": accumulated_usage}

    col = _get_collection()
    phase = state.get("phase", "input")
    situation = state.get("situation", "")
    issues = list(state.get("issues", []))
    selected_issue = state.get("selected_issue", "")
    qa_list = list(state.get("qa_list", []))
    articles_by_issue = dict(state.get("articles_by_issue", {}))
    checklist = list(state.get("checklist") or [])
    checklist_index = state.get("checklist_index", 0)
    _fs = state.get("filter_sources")
    filter_sources = _fs if (_fs and isinstance(_fs, list)) else ALL_LABOR_LAW_SOURCES

    # 새 상황 입력
    if phase == "input" or (not situation and user_text):
        # 노동법과 무관한 질문인지 빠르게 확인 (키워드 기반, LLM 호출 없음 → TTFT 단축)
        try:
            _is_labor, _reason = is_labor_law_related_fast(user_text)
            if not _is_labor:
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
                    "usage": accumulated_usage,
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
                    filter_sources=filter_sources,
                    exclude_sections=["벌칙", "부칙"],
                )
                if search_results:
                    rag_context = _rag_context(search_results, max_length=2000)
                    overrides = state.get("prompt_overrides") or {}
                    sys_k = overrides.get("system_knowledge_qa") or system_knowledge_qa()
                    user_k = overrides.get("user_knowledge_qa") or user_knowledge_qa(user_text, rag_context)
                    res_meta = chat_with_metadata(sys_k, user_k, max_tokens=1000)
                    answer = res_meta["content"]
                    if not (answer and str(answer).strip()):
                        # RAG 조문만으로 재요청 후, 그래도 없으면 검색된 조문 본문 그대로 노출
                        answer = _knowledge_empty_fallback(user_text, rag_context)
                    accumulated_usage = _merge_usage(accumulated_usage, res_meta.get("usage"))
                    debug_info = {"knowledge_qa": res_meta}
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
                        "debug_info": debug_info,
                        "usage": accumulated_usage,
                    }
            except Exception:
                # 지식 질문인데 오류 발생 → 체크리스트 없이 바로 답변만 반환
                return {
                    "messages": [AIMessage(content="질문 처리 중 오류가 발생했습니다. 다시 질문해 주세요.")],
                    "situation": "",
                    "issues": [],
                    "phase": "input",
                    "usage": accumulated_usage,
                }
        
        # 1.5 서류·서식 질문 (국가법령정보 licbyl/admbyl API)
        elif question_type == "documents":
            try:
                from rag.api_documents import search_documents_for_topic, format_documents_answer
                # 검색어: 서류 관련 표현 제거 후 첫 의미 있는 단어(2자 이상) 또는 전체
                query = user_text.strip()
                for w in ("필요한 서류", "필요 서류", "제출서류", "서식", "서류", "양식", "별표", "뭐가", "무엇", "어떤", "무슨", "가 필요", "가 있나", "가 있나요", "?"):
                    query = query.replace(w, " ").strip()
                query = query or user_text.strip() or "근로"
                # API는 법령명/서식명 검색이므로 긴 문장보다 짧은 키워드가 유리: 첫 단어 사용
                first_word = (query.split() or [query])[0].strip()
                if len(first_word) >= 2:
                    query = first_word
                docs = search_documents_for_topic(query, display=15)
                topic = query[:30] if len(query) > 30 else query
                answer = format_documents_answer(docs, topic)
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
                    "usage": accumulated_usage,
                }
            except Exception:
                return {
                    "messages": [AIMessage(content="서류·서식 조회 중 오류가 발생했습니다. 국가법령정보센터(www.law.go.kr)에서 검색해 보시거나, 다른 질문을 해 주세요.")],
                    "situation": "",
                    "phase": "input",
                    "usage": accumulated_usage,
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
                        calc_section = f"""📅 근무 기간: {calc_result['work_days']}일 ({calc_result['work_years']}년)
💰 월 평균임금: {calc_result['monthly_salary']:,.0f}원
📊 계산식: {calc_result['formula']}

**예상 퇴직금: 약 {calc_result['estimated_severance']:,}원**

⚠️ {calc_result['note']}
정확한 계산을 위해서는 최근 3개월간의 임금 총액과 각종 수당을 포함한 평균임금이 필요합니다."""
                        answer = _prepend_rag_for_calculation(col, user_text, calc_section, "퇴직금 평균임금 재직일수 제34조", filter_sources)
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
                        calc_section = f"""⏰ 기본 근무: {calc_result['base_hours']}시간 → {calc_result['base_pay']:,}원
🌙 연장 근무: {calc_result['overtime_hours']}시간 → {calc_result['overtime_pay']:,}원 (시급의 150%)

**총 수당: {calc_result['total_pay']:,}원**

📋 계산식: {calc_result['formula']}

💡 {calc_result['note']}"""
                        answer = _prepend_rag_for_calculation(col, user_text, calc_section, "연장근로 수당 가산 제56조", filter_sources)
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
                else:
                    # 계산 질문이지만 패턴 매칭 실패 → 상황 경로 시도(수습/최저임금 등)
                    try:
                        from rag.context import openai_api_key_ctx, law_api_key_ctx
                        curr_okey = openai_api_key_ctx.get()
                        curr_lkey = law_api_key_ctx.get()
                        issues_fb, step1_articles_fb, _ = step1_issue_classification(
                            user_text, collection=col, openai_api_key=curr_okey, law_api_key=curr_lkey
                        )
                        if issues_fb:
                            sel_issue = issues_fb[0]
                            articles_fb = dict(step1_articles_fb) if step1_articles_fb else {}
                            remaining_fb = list(articles_fb.get(sel_issue) or [])
                            step2_fb = step2_checklist(
                                sel_issue, (user_text[:400] if isinstance(user_text, str) else ""),
                                collection=col, narrow_answers=None, qa_list=[], remaining_articles=remaining_fb,
                                openai_api_key=curr_okey
                            )
                            checklist_fb = step2_fb.get("checklist", []) if isinstance(step2_fb, dict) else []
                            if checklist_fb:
                                resp_fb = f"감지된 이슈: {', '.join(issues_fb)}\n\n체크리스트가 생성되었습니다. 아래에서 각 질문에 대해 **네** / **아니요** / **모르겠음** 버튼을 눌러 주세요."
                                return {
                                    "messages": [AIMessage(content=resp_fb)],
                                    "situation": user_text, "issues": issues_fb, "selected_issue": sel_issue,
                                    "qa_list": [], "articles_by_issue": articles_fb,
                                    "checklist": checklist_fb, "checklist_index": 0,
                                    "phase": "checklist", "pending_question": "",
                                    "checklist_rag_results": step2_fb.get("rag_results", []) if isinstance(step2_fb, dict) else [],
                                }
                    except Exception:
                        pass
                    # 상황 경로 실패 시 RAG로 답변
                    try:
                        search_results = search(
                            col, user_text, top_k=5,
                            filter_sources=filter_sources,
                        )
                        if search_results:
                            rag_context = _rag_context(search_results, max_length=2000)
                            overrides = state.get("prompt_overrides") or {}
                            sys_c = overrides.get("system_calculation_qa") or system_calculation_qa()
                            user_c = overrides.get("user_calculation_qa") or user_calculation_qa(user_text, rag_context)
                            res_meta = chat_with_metadata(sys_c, user_c, max_tokens=1500)
                            answer = res_meta["content"]
                            if not answer or not answer.strip():
                                answer = _calculation_empty_fallback(user_text, rag_context)
                            accumulated_usage = _merge_usage(accumulated_usage, res_meta.get("usage"))
                            debug_info = {"calculation_qa": res_meta}
                            return {
                                "messages": [AIMessage(content=answer)],
                                "situation": "",
                                "issues": [],
                                "phase": "input",
                                "debug_info": debug_info,
                                "usage": accumulated_usage,
                            }
                        else:
                            # 검색 결과 없으면 넓게 한 번 더 검색
                            search_results2 = search(
                                col, "퇴직금 연장근로 수당 평균임금", top_k=3,
                                filter_sources=filter_sources,
                            )
                            if search_results2:
                                rag_context2 = _rag_context(search_results2, max_length=2000)
                                answer = _calculation_empty_fallback(user_text, rag_context2)
                            else:
                                answer = "검색된 조문이 없습니다. 구체적인 입사일, 퇴사일, 월급(또는 시급·근무시간)을 적어 주시면 계산해 드립니다."
                            return {
                                "messages": [AIMessage(content=answer)],
                                "situation": "",
                                "issues": [],
                                "phase": "input",
                            }
                    except Exception as e:
                        import traceback
                        import sys
                        import os
                        _DEBUG = os.getenv("LAW_DEBUG", "0") == "1"
                        if _DEBUG:
                            print(f"[계산 질문 처리 오류] {e}\n{traceback.format_exc()}", file=sys.stderr)
                        return {
                            "messages": [AIMessage(content="계산 질문 처리 중 오류가 발생했습니다. 다시 질문해 주세요.")],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
            except Exception as e:
                return {
                    "messages": [AIMessage(content="계산 질문 처리 중 오류가 발생했습니다. 다시 질문해 주세요.")],
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
                        filter_sources=filter_sources,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    
                    # RAG 기반 답변 생성
                    overrides = state.get("prompt_overrides") or {}
                    sys_e = overrides.get("system_exception_qa") or system_exception_qa()
                    user_e = overrides.get("user_exception_qa") or user_exception_qa(user_text, rag_context)
                    answer = chat(
                        sys_e,
                        user_e,
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
                        filter_sources=filter_sources,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    overrides = state.get("prompt_overrides") or {}
                    sys_e = overrides.get("system_exception_qa") or system_exception_qa()
                    user_e = overrides.get("user_exception_qa") or user_exception_qa(user_text, rag_context)
                    res_meta = chat_with_metadata(
                        sys_e,
                        user_e,
                        max_tokens=None  # reasoning 모델이 충분히 답변하도록 제한 없음
                    )
                    answer = res_meta["content"]
                    
                    # 최신성 확인 질문인 경우 데이터 연도 추가
                    if any(kw in user_text for kw in ["올해", "2026", "2025", "2024", "최신"]):
                        answer += "\n\n📅 **데이터 참고사항:** 제공된 법령 데이터는 동기화 시점의 법령을 기준으로 합니다. 법령은 개정될 수 있으므로, 최신 법령 확인이 필요하시면 국가법령정보센터(www.law.go.kr)를 참고하시기 바랍니다."
                    accumulated_usage = _merge_usage(accumulated_usage, res_meta.get("usage"))
                debug_info = {"exception_qa": res_meta}
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
                    "debug_info": debug_info,
                    "usage": accumulated_usage,
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
        # ★ step1 + step2 병렬 실행으로 TTFT 단축 (keyword 경로에서 효과 큼)
        situation = user_text
        from rag.context import openai_api_key_ctx, law_api_key_ctx
        curr_okey = openai_api_key_ctx.get()
        curr_lkey = law_api_key_ctx.get()
        overrides = state.get("prompt_overrides") or {}
        search_top_k = state.get("top_k") or 22
        parallel_result = step1_and_step2_parallel(
            situation, collection=col, top_k=search_top_k,
            openai_api_key=curr_okey, law_api_key=curr_lkey,
            prompt_overrides=overrides,
        )
        issues = parallel_result.get("issues", [])
        if not issues:
            return {
                "messages": [AIMessage(content="제공된 법령 데이터에서 해당 상황에 맞는 이슈를 찾지 못했습니다.\n\n직장에서 겪고 계신 구체적인 문제를 말씀해 주시면 더 정확한 상담을 도와드릴 수 있습니다. 예: '월급을 못 받았어요', '해고당했어요', '연차휴가를 사용하지 못했어요'")],
                "situation": situation,
                "issues": [],
                "phase": "input",
                "usage": accumulated_usage,
            }
        selected_issue = parallel_result.get("selected_issue", issues[0])
        articles_by_issue = parallel_result.get("articles_by_issue", {})
        checklist = parallel_result.get("checklist", [])
        qa_list = []
        if checklist:
            # 말풍선에는 안내만. 질문 전문은 앱 아래 '체크리스트 답변' 영역에만 표시
            resp = f"감지된 이슈: {', '.join(issues)}\n\n체크리스트가 생성되었습니다. 아래에서 각 질문에 대해 **네** / **아니요** / **모르겠음** 버튼을 눌러 주세요."
            return {
                "messages": [AIMessage(content=resp)],
                "situation": situation, "issues": issues, "selected_issue": selected_issue,
                "qa_list": qa_list, "articles_by_issue": articles_by_issue,
                "checklist": checklist, "checklist_index": 0,
                "phase": "checklist", "pending_question": "",
                "checklist_rag_results": parallel_result.get("rag_results", []),
                "usage": accumulated_usage,
            }
        narrow_answers = []
        overrides = state.get("prompt_overrides") or {}
        res = step3_conclusion(
            selected_issue, qa_list, collection=col, narrow_answers=None,
            prompt_overrides=overrides,
            language=state.get("language"), tone=state.get("tone"),
        )
        conc = res.get("conclusion", res) if isinstance(res, dict) else str(res)
        rel = res.get("related_articles", []) if isinstance(res, dict) else []
        tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
        llm_usage = (res.get("debug_info") or {}).get("llm_conclusion") or {}
        if isinstance(llm_usage, dict) and llm_usage.get("usage"):
            accumulated_usage = _merge_usage(accumulated_usage, llm_usage["usage"])
        return {
            "messages": [AIMessage(content=f"감지된 이슈: {', '.join(issues)}\n\n**결론**\n\n{conc}{tail}")],
            "situation": situation, "issues": issues, "selected_issue": selected_issue,
            "qa_list": qa_list, "phase": "conclusion", "pending_question": "",
            "usage": accumulated_usage,
        }

    # checklist 답변은 앱에서 버튼(네/아니요/모르겠음)으로 수집 후 step3/step2 호출하므로 그래프에서는 처리하지 않음
    
    # checklist 단계 처리
    if phase == "checklist":
        # 인텐트 판별 (새 질문인지, 체크리스트 답변인지)
        intent = _detect_intent(user_text, state)
        
        if intent == "answer_checklist":
            # 앱에서 보낸 멀티라인 답변 파싱 ("질문: 답변")
            new_qa = []
            for line in user_text.split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    new_qa.append({"question": parts[0].strip(), "answer": parts[1].strip()})
            
            if new_qa:
                qa_list = new_qa
                from rag.context import openai_api_key_ctx
                curr_okey = openai_api_key_ctx.get()
                
                # 결론 도출 (Step 3)
                overrides = state.get("prompt_overrides") or {}
                res = step3_conclusion(
                    selected_issue, qa_list, 
                    collection=col, 
                    narrow_answers=None,
                    prompt_overrides=overrides,
                    openai_api_key=curr_okey,
                    language=state.get("language"), tone=state.get("tone"),
                )
                conc = res.get("conclusion", res) if isinstance(res, dict) else str(res)
                rel = res.get("related_articles", []) if isinstance(res, dict) else []
                tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
                llm_usage = (res.get("debug_info") or {}).get("llm_conclusion") or {}
                if isinstance(llm_usage, dict) and llm_usage.get("usage"):
                    accumulated_usage = _merge_usage(accumulated_usage, llm_usage["usage"])
                return {
                    "messages": [AIMessage(content=f"감지된 이슈: {', '.join(issues)}\n\n**결론**\n\n{conc}{tail}")],
                    "situation": situation, "issues": issues, "selected_issue": selected_issue,
                    "qa_list": qa_list, "phase": "conclusion", "pending_question": "",
                    "articles_by_issue": articles_by_issue,
                    "usage": accumulated_usage,
                }

        # 답변이 아닌 경우 (새로운 노동법 질문 등) -> 기존 로직 (Restart)
        # 노동법과 무관한 질문인지 빠르게 확인 (키워드 기반, LLM 호출 없음 → TTFT 단축)
        try:
            _is_labor, _reason = is_labor_law_related_fast(user_text)
            if not _is_labor:
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
                    filter_sources=filter_sources,
                    exclude_sections=["벌칙", "부칙"],
                )
                if search_results:
                    rag_context = _rag_context(search_results, max_length=2000)
                    answer = chat(
                        system_knowledge_qa(),
                        user_knowledge_qa(user_text, rag_context),
                        max_tokens=1000
                    )
                    if not (answer and str(answer).strip()):
                        answer = _knowledge_empty_fallback(user_text, rag_context)
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
        
        elif question_type == "documents":
            try:
                from rag.api_documents import search_documents_for_topic, format_documents_answer
                query = user_text.strip()
                for w in ("필요한 서류", "필요 서류", "제출서류", "서식", "서류", "양식", "별표", "뭐가", "무엇", "어떤", "무슨", "가 필요", "가 있나", "가 있나요", "?"):
                    query = query.replace(w, " ").strip()
                query = query or user_text.strip() or "근로"
                first_word = (query.split() or [query])[0].strip()
                if len(first_word) >= 2:
                    query = first_word
                docs = search_documents_for_topic(query, display=15)
                topic = query[:30] if len(query) > 30 else query
                answer = format_documents_answer(docs, topic)
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
                    "usage": accumulated_usage,
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
                        calc_section = f"""📅 근무 기간: {calc_result['work_days']}일 ({calc_result['work_years']}년)
💰 월 평균임금: {calc_result['monthly_salary']:,.0f}원
📊 계산식: {calc_result['formula']}

**예상 퇴직금: 약 {calc_result['estimated_severance']:,}원**

⚠️ {calc_result['note']}
정확한 계산을 위해서는 최근 3개월간의 임금 총액과 각종 수당을 포함한 평균임금이 필요합니다."""
                        answer = _prepend_rag_for_calculation(col, user_text, calc_section, "퇴직금 평균임금 재직일수 제34조", filter_sources)
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
                        calc_section = f"""⏰ 기본 근무: {calc_result['base_hours']}시간 → {calc_result['base_pay']:,}원
🌙 연장 근무: {calc_result['overtime_hours']}시간 → {calc_result['overtime_pay']:,}원 (시급의 150%)

**총 수당: {calc_result['total_pay']:,}원**

📋 계산식: {calc_result['formula']}

💡 {calc_result['note']}"""
                        answer = _prepend_rag_for_calculation(col, user_text, calc_section, "연장근로 수당 가산 제56조")
                        return {
                            "messages": [AIMessage(content=answer)],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
                else:
                    # 계산 질문이지만 패턴 매칭 실패 → 상황 경로 시도(수습/최저임금 등)
                    try:
                        from rag.context import openai_api_key_ctx, law_api_key_ctx
                        curr_okey = openai_api_key_ctx.get()
                        curr_lkey = law_api_key_ctx.get()
                        issues_fb2, step1_articles_fb2, _ = step1_issue_classification(
                            user_text, collection=col, openai_api_key=curr_okey, law_api_key=curr_lkey
                        )
                        if issues_fb2:
                            sel_issue2 = issues_fb2[0]
                            articles_fb2 = dict(step1_articles_fb2) if step1_articles_fb2 else {}
                            remaining_fb2 = list(articles_fb2.get(sel_issue2) or [])
                            step2_fb2 = step2_checklist(
                                sel_issue2, (user_text[:400] if isinstance(user_text, str) else ""),
                                collection=col, narrow_answers=None, qa_list=[], remaining_articles=remaining_fb2,
                                openai_api_key=curr_okey
                            )
                            checklist_fb2 = step2_fb2.get("checklist", []) if isinstance(step2_fb2, dict) else []
                            if checklist_fb2:
                                resp_fb2 = f"감지된 이슈: {', '.join(issues_fb2)}\n\n체크리스트가 생성되었습니다. 아래에서 각 질문에 대해 **네** / **아니요** / **모르겠음** 버튼을 눌러 주세요."
                                return {
                                    "messages": [AIMessage(content=resp_fb2)],
                                    "situation": user_text, "issues": issues_fb2, "selected_issue": sel_issue2,
                                    "qa_list": [], "articles_by_issue": articles_fb2,
                                    "checklist": checklist_fb2, "checklist_index": 0,
                                    "phase": "checklist", "pending_question": "",
                                    "checklist_rag_results": step2_fb2.get("rag_results", []) if isinstance(step2_fb2, dict) else [],
                                }
                    except Exception:
                        pass
                    try:
                        search_results = search(
                            col, user_text, top_k=5,
                            filter_sources=filter_sources,
                        )
                        if search_results:
                            rag_context = _rag_context(search_results, max_length=2000)
                            overrides = state.get("prompt_overrides") or {}
                            sys_c = overrides.get("system_calculation_qa") or system_calculation_qa()
                            user_c = overrides.get("user_calculation_qa") or user_calculation_qa(user_text, rag_context)
                            answer = chat(sys_c, user_c, max_tokens=1500)
                            if not answer or not answer.strip():
                                answer = _calculation_empty_fallback(user_text, rag_context)
                            return {
                                "messages": [AIMessage(content=answer)],
                                "situation": "",
                                "issues": [],
                                "phase": "input",
                            }
                        else:
                            search_results2 = search(
                                col, "퇴직금 연장근로 수당 평균임금", top_k=3,
                                filter_sources=filter_sources,
                            )
                            if search_results2:
                                rag_context2 = _rag_context(search_results2, max_length=2000)
                                answer = _calculation_empty_fallback(user_text, rag_context2)
                            else:
                                answer = "검색된 조문이 없습니다. 구체적인 입사일, 퇴사일, 월급(또는 시급·근무시간)을 적어 주시면 계산해 드립니다."
                            return {
                                "messages": [AIMessage(content=answer)],
                                "situation": "",
                                "issues": [],
                                "phase": "input",
                            }
                    except Exception as e:
                        import traceback
                        import sys
                        import os
                        _DEBUG = os.getenv("LAW_DEBUG", "0") == "1"
                        if _DEBUG:
                            print(f"[계산 질문 처리 오류] {e}\n{traceback.format_exc()}", file=sys.stderr)
                        return {
                            "messages": [AIMessage(content="계산 질문 처리 중 오류가 발생했습니다. 다시 질문해 주세요.")],
                            "situation": "",
                            "issues": [],
                            "phase": "input",
                        }
            except Exception:
                pass
        
        elif question_type == "exception":
            try:
                overrides = state.get("prompt_overrides") or {}
                if any(kw in user_text for kw in ["몰래", "기밀", "빼돌려"]):
                    search_query = "해고 사유 정당한 해고 퇴직금 계약 위반 근로계약"
                    search_results = search(
                        col, search_query, top_k=5,
                        filter_sources=filter_sources,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    sys_e = overrides.get("system_exception_qa") or system_exception_qa()
                    user_e = overrides.get("user_exception_qa") or user_exception_qa(user_text, rag_context)
                    answer = chat(
                        sys_e,
                        user_e,
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
                        filter_sources=filter_sources,
                    )
                    rag_context = _rag_context(search_results, max_length=2000) if search_results else ""
                    sys_e = overrides.get("system_exception_qa") or system_exception_qa()
                    user_e = overrides.get("user_exception_qa") or user_exception_qa(user_text, rag_context)
                    answer = chat(
                        sys_e,
                        user_e,
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
                    "usage": accumulated_usage,
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
