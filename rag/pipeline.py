# RAG 기반 노동법 상담 파이프라인
# 1. 상황 입력 -> 이슈 분류(멀티)  2. 이슈별 조항 좁히기 + 구분 질문
# 3. 체크리스트 생성(숫자/요건)  4. Q&A 기반 결론
from typing import List, Dict, Any, Optional

from rag.store import build_vector_store, search
from rag.prompts import (
    system_issue_classification,
    user_issue_classification,
    system_provision_narrow,
    user_provision_narrow,
    system_checklist,
    user_checklist,
    system_conclusion,
    user_conclusion,
)
from rag.llm import chat, chat_json


def _rag_context(search_results: List[Dict[str, Any]]) -> str:
    return "\n\n---\n\n".join(r.get("text", "") for r in search_results)


def step1_issue_classification(
    situation: str,
    collection=None,
    top_k: int = 15,
) -> List[str]:
    """사용자 상황 -> RAG 검색 -> 이슈 분류 (멀티 이슈)."""
    if collection is None:
        collection = build_vector_store()
    results = search(collection, situation, top_k=top_k)
    if not results:
        return []
    context = _rag_context(results)
    out = chat_json(system_issue_classification(), user_issue_classification(situation, context))
    if isinstance(out, list):
        return [x for x in out if isinstance(x, str)]
    if isinstance(out, dict) and "issues" in out:
        return out["issues"]
    return []


def step2_provision_narrow(
    issue: str,
    collection=None,
    top_k: int = 12,
) -> Dict[str, Any]:
    """이슈에 따른 조항 좁히기: 카테고리 + 구분 질문."""
    if collection is None:
        collection = build_vector_store()
    results = search(collection, issue, top_k=top_k)
    if not results:
        return {"categories": [], "questions": []}
    context = _rag_context(results)
    out = chat_json(system_provision_narrow(), user_provision_narrow(issue, context))
    if isinstance(out, dict):
        return {
            "categories": out.get("categories", []),
            "questions": out.get("questions", []),
        }
    return {"categories": [], "questions": []}


def step3_checklist(
    issue: str,
    filtered_provisions_text: str,
    collection=None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """걸러진 조항 기준 체크리스트 (숫자·요건 검사 질문)."""
    if collection is None:
        collection = build_vector_store()
    results = search(collection, issue + " " + filtered_provisions_text[:500], top_k=top_k)
    context = _rag_context(results)
    out = chat_json(system_checklist(), user_checklist(issue, context, filtered_provisions_text))
    if isinstance(out, list):
        return out
    if isinstance(out, dict) and "checklist" in out:
        return out["checklist"]
    return []


def step4_conclusion(
    issue: str,
    qa_list: List[Dict[str, str]],
    collection=None,
    top_k: int = 10,
) -> str:
    """모든 질문·대답과 RAG 조문 기반 결론 (법조항 인용)."""
    if collection is None:
        collection = build_vector_store()
    qa_text = "\n".join(f"Q: {x.get('q', x.get('question', ''))}\nA: {x.get('a', x.get('answer', ''))}" for x in qa_list)
    results = search(collection, issue, top_k=top_k)
    context = _rag_context(results)
    return chat(system_conclusion(), user_conclusion(issue, qa_text, context))
