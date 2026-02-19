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
)
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
