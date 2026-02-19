# -*- coding: utf-8 -*-
"""LangGraph 기반 노동법 RAG 챗봇 그래프"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict, Annotated, Literal
from operator import add

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
)
from rag.law_json import get_related_terms_and_definition_terms, rerank_definition_results
from config import (
    SOURCE_LAW,
    RAG_MAIN_TOP_K,
    RAG_AUX_TOP_K,
    RAG_DEF_TOP_K,
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
        situation = user_text
        issues, step1_articles, _ = step1_issue_classification(situation, collection=col)
        if not issues:
            return {
                "messages": [AIMessage(content="제공된 법령 데이터에서 해당 상황에 맞는 이슈를 찾지 못했습니다.")],
                "situation": situation,
                "issues": [],
                "phase": "input",
            }
        selected_issue = issues[0]
        # step1에서 반환한 이슈별 조문 사용, 없으면 이슈별 검색
        articles_by_issue = dict(step1_articles) if step1_articles else {}
        for iss in issues[:3]:
            if iss in articles_by_issue and articles_by_issue[iss]:
                continue
            seen = set()
            arts = []
            terms_tuple, def_tuple = get_related_terms_and_definition_terms(iss)
            terms_set = set(terms_tuple)
            def_terms = set(def_tuple)
            expand = " ".join(terms_set)
            queries_main = [q for q in [iss, situation, expand] if (q or "").strip()]

            def _main_search():
                out = []
                for q in queries_main:
                    out.extend(search(
                        col, q, top_k=RAG_MAIN_TOP_K, filter_sources=[SOURCE_LAW],
                        exclude_sections=["벌칙", "부칙"], exclude_chapters=["제1장 총칙"],
                    ))
                return out

            def _aux_search():
                q_extra = f"{iss} {expand}".strip() or iss
                return search(
                    col, q_extra, top_k=RAG_AUX_TOP_K, filter_sources=[SOURCE_LAW],
                    exclude_sections=["벌칙", "부칙"],
                )

            def _def_search():
                if not def_terms:
                    return []
                q_def = " ".join(def_terms)
                res = search(
                    col, q_def, top_k=RAG_DEF_TOP_K, filter_sources=[SOURCE_LAW],
                    exclude_sections=["벌칙", "부칙"],
                )
                return rerank_definition_results(res, def_terms, top_terms=["정의", "평균임금"])

            with ThreadPoolExecutor(max_workers=3) as ex:
                fut_main = ex.submit(_main_search)
                fut_aux = ex.submit(_aux_search)
                fut_def = ex.submit(_def_search)
                for fut in as_completed([fut_main, fut_aux, fut_def]):
                    for r in fut.result():
                        a = r.get("article", "")
                        if a and a not in seen:
                            arts.append(r)
                            seen.add(a)
            arts = filter_articles_by_issue_relevance(iss, arts, top_k=RAG_FILTER_TOP_K)
            articles_by_issue[iss] = arts
        qa_list = []
        # 이슈 선택 후 바로 체크리스트
        remaining = articles_by_issue.get(selected_issue) or []
        filter_text = (situation + " " + selected_issue)[:500]
        step2_res = step2_checklist(
            selected_issue, filter_text, collection=col,
            narrow_answers=None,
            qa_list=qa_list,
            remaining_articles=remaining,
        )
        checklist = step2_res.get("checklist", []) if isinstance(step2_res, dict) else (step2_res or [])
        if checklist:
            q0 = (checklist[0].get("question") or checklist[0].get("item") or str(checklist[0]))
            resp = f"**감지된 이슈:** {', '.join(issues)}\n\n체크리스트 질문:\n**1.** {q0}\n\n(답변을 입력해 주세요)"
            return {
                "messages": [AIMessage(content=resp)],
                "situation": situation, "issues": issues, "selected_issue": selected_issue,
                "qa_list": qa_list, "articles_by_issue": articles_by_issue,
                "checklist": checklist, "checklist_index": 0,
                "phase": "checklist", "pending_question": q0,
            }
        res = step3_conclusion(selected_issue, qa_list, collection=col)
        conc = res.get("conclusion", res) if isinstance(res, dict) else str(res)
        rel = res.get("related_articles", []) if isinstance(res, dict) else []
        tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
        return {
            "messages": [AIMessage(content=f"**감지된 이슈:** {', '.join(issues)}\n\n**결론**\n\n{conc}{tail}")],
            "situation": situation, "issues": issues, "selected_issue": selected_issue,
            "qa_list": qa_list, "phase": "conclusion", "pending_question": "",
        }

    # checklist 답변
    if phase == "checklist" and checklist:
        pending_q = state.get("pending_question", "")
        qa_list = list(qa_list) + [{"question": pending_q, "answer": user_text}]
        idx = checklist_index + 1
        if idx >= len(checklist):
            res = step3_conclusion(selected_issue, qa_list, collection=col,
                                  narrow_answers=[x.get("answer", "").strip() for x in qa_list])
            conc = res.get("conclusion", res) if isinstance(res, dict) else str(res)
            rel = res.get("related_articles", []) if isinstance(res, dict) else []
            tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
            return {
                "messages": [AIMessage(content=f"**결론**\n\n{conc}{tail}")],
                "qa_list": qa_list, "checklist_index": idx,
                "phase": "conclusion", "pending_question": "",
            }
        next_q = (checklist[idx].get("question") or checklist[idx].get("item") or str(checklist[idx]))
        resp = f"**{idx+1}.** {next_q}\n\n(답변을 입력해 주세요)"
        return {
            "messages": [AIMessage(content=resp)],
            "qa_list": qa_list, "checklist_index": idx,
            "phase": "checklist", "pending_question": next_q,
        }

    # 새 상담 시작
    return {
        "messages": [AIMessage(content="새로운 상황을 말씀해 주세요. 예: 퇴직금을 못 받았어요")],
        "situation": "", "issues": [], "selected_issue": "", "qa_list": [],
        "articles_by_issue": {}, "phase": "input", "pending_question": "",
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
