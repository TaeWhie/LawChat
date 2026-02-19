"""
노동법 RAG 챗봇 - LangGraph + Streamlit 챗봇 UI (실제 서비스용)
app.py와 동일: 체크리스트는 한 번에 표시하고 네/아니요/모르겠음 버튼으로 답하며, 여러 차수(라운드) 지원.
"""
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from rag.law_json import SCENARIO_QUICK, get_chapters, get_articles_by_chapter

CHECKLIST_MAX_ROUNDS = 3  # app.py와 동일

# 사용자에게 보여줄 고정 메시지 (기술적 오류 내용 노출 방지)
USER_FACING_ERROR = "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
LOAD_ERROR_MESSAGE = "서비스를 불러오는 중 문제가 발생했습니다. 새로고침 후 다시 시도해 주세요."


def init_session():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "thread_id" not in st.session_state:
        import uuid
        st.session_state.thread_id = str(uuid.uuid4())[:8]
    if "graph_load_error" not in st.session_state:
        st.session_state.graph_load_error = None
    # 체크리스트 버튼 방식 (app.py와 동일)
    if "cb_checklist" not in st.session_state:
        st.session_state.cb_checklist = []
    if "cb_checklist_answers" not in st.session_state:
        st.session_state.cb_checklist_answers = {}
    if "cb_issue" not in st.session_state:
        st.session_state.cb_issue = ""
    if "cb_situation" not in st.session_state:
        st.session_state.cb_situation = ""
    if "cb_articles_by_issue" not in st.session_state:
        st.session_state.cb_articles_by_issue = {}
    if "cb_round" not in st.session_state:
        st.session_state.cb_round = 1
    if "cb_all_qa" not in st.session_state:
        st.session_state.cb_all_qa = []
    if "cb_checklist_rag_results" not in st.session_state:
        st.session_state.cb_checklist_rag_results = []


def get_graph_safe():
    """그래프 로드. 실패 시 None 반환하고 session_state.graph_load_error에 메시지 저장."""
    if st.session_state.get("graph_load_error"):
        return None
    try:
        from rag.graph import get_graph
        return get_graph()
    except Exception:
        st.session_state.graph_load_error = LOAD_ERROR_MESSAGE
        return None


def main():
    st.set_page_config(page_title="노동법 챗봇", layout="wide")
    init_session()

    graph = get_graph_safe()
    thread_id = st.session_state.thread_id

    # 사이드바
    with st.sidebar:
        st.header("설정")
        if st.session_state.get("graph_load_error"):
            st.error(st.session_state.graph_load_error)
        if st.button("🔄 새 대화 시작"):
            st.session_state.messages = []
            st.session_state.pending_buttons = []
            st.session_state.graph_load_error = None
            st.session_state.cb_checklist = []
            st.session_state.cb_checklist_answers = {}
            st.session_state.cb_issue = ""
            st.session_state.cb_situation = ""
            st.session_state.cb_articles_by_issue = {}
            st.session_state.cb_round = 1
            st.session_state.cb_all_qa = []
            st.session_state.cb_checklist_rag_results = []
            import uuid
            st.session_state.thread_id = str(uuid.uuid4())[:8]
            st.rerun()
        st.divider()
        st.subheader("📚 장별 둘러보기")
        try:
            chapters = get_chapters()[:12]
        except Exception:
            chapters = []
        for ch in chapters:
            with st.expander(f"{ch['number']} {ch['title']}", expanded=False):
                for a in get_articles_by_chapter(ch["number"]) or []:
                    st.caption(f"· {a.get('article_number','')} {a.get('title','')}")

    st.title("⚖️ 노동법 RAG 챗봇")
    st.caption("근로기준법 기반 상담. 상황을 말씀해 주세요.")

    # 시나리오 버튼
    st.caption("시나리오:")
    cols = st.columns(4)
    for i, s in enumerate(SCENARIO_QUICK[:4]):
        with cols[i]:
            if st.button(s["label"], key=f"btn_{s['label']}"):
                st.session_state.messages.append(HumanMessage(content=s.get("situation", s["label"])))
                st.rerun()

    # 채팅 히스토리 표시
    for msg in st.session_state.messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        with st.chat_message(role):
            st.markdown(msg.content)

    # 체크리스트: 말풍선에 이미 질문이 있으므로 여기서는 번호 + 버튼만 (질문 문장 중복 제거)
    cb_checklist = st.session_state.get("cb_checklist") or []
    cb_answers = st.session_state.get("cb_checklist_answers") or {}
    if cb_checklist and st.session_state.messages and isinstance(st.session_state.messages[-1], AIMessage):
        st.markdown("**체크리스트 답변** (위 질문에 대해 각각 버튼을 눌러 주세요)")
        for i, item in enumerate(cb_checklist):
            current = cb_answers.get(i, "").strip()
            st.caption(f"질문 {i+1}")
            c1, c2, c3, _ = st.columns([1, 1, 1, 2])
            with c1:
                if st.button("네", key=f"cb_btn_{i}_0", type="primary" if current == "네" else "secondary"):
                    cb_answers[i] = "네"
                    st.session_state.cb_checklist_answers = dict(cb_answers)
                    st.rerun()
            with c2:
                if st.button("아니요", key=f"cb_btn_{i}_1", type="primary" if current == "아니요" else "secondary"):
                    cb_answers[i] = "아니요"
                    st.session_state.cb_checklist_answers = dict(cb_answers)
                    st.rerun()
            with c3:
                if st.button("모르겠음", key=f"cb_btn_{i}_2", type="primary" if current == "모르겠음" else "secondary"):
                    cb_answers[i] = "모르겠음"
                    st.session_state.cb_checklist_answers = dict(cb_answers)
                    st.rerun()
            if current:
                st.caption(f"선택: **{current}**")
        st.divider()

        # 모든 질문에 답했으면 app.py와 동일하게 should_continue 판단 → 2차 체크리스트 또는 결론
        if len(cb_answers) == len(cb_checklist):
            full_qa = [
                {"question": (cb_checklist[i].get("question") or cb_checklist[i].get("item") or ""), "answer": cb_answers.get(i, "")}
                for i in range(len(cb_checklist))
            ]
            all_qa = list(st.session_state.get("cb_all_qa") or []) + full_qa
            cb_issue = st.session_state.get("cb_issue", "")
            cb_situation = st.session_state.get("cb_situation", "")
            cb_articles = st.session_state.get("cb_articles_by_issue") or {}
            cb_round = st.session_state.get("cb_round", 1)
            prev_rag = st.session_state.get("cb_checklist_rag_results") or []
            remaining = list(prev_rag) if prev_rag else list(cb_articles.get(cb_issue) or [])

            try:
                from rag.store import build_vector_store, search
                from rag.pipeline import step2_checklist, step3_conclusion
                from config import ALL_LABOR_LAW_SOURCES
                col = build_vector_store()[0]
                narrow_answers = [x.get("answer", "").strip() for x in all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
                filter_text = (cb_issue + " " + "\n".join(f"Q: {x['question']} A: {x['answer']}" for x in all_qa))[:400]
                # app.py와 동일: 2차 이상이면 이전 조문 + 새 검색 결과 병합 후 step2
                query = (cb_issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else cb_issue
                new_results = search(
                    col, query, top_k=12,
                    filter_sources=ALL_LABOR_LAW_SOURCES,
                    exclude_sections=["벌칙", "부칙"],
                    exclude_chapters=["제1장 총칙"],
                )
                seen_art = {r.get("article", "") for r in remaining}
                merged = list(remaining)
                for r in new_results:
                    a = r.get("article", "")
                    if a and a not in seen_art:
                        merged.append(r)
                        seen_art.add(a)
                step2_res = step2_checklist(
                    cb_issue, filter_text, collection=col,
                    narrow_answers=narrow_answers or None,
                    qa_list=all_qa,
                    remaining_articles=merged,
                )
                should_continue = step2_res.get("should_continue", False)
                continuation_reason = step2_res.get("continuation_reason", "")
                new_checklist = step2_res.get("checklist", []) or []

                if should_continue and new_checklist and cb_round < CHECKLIST_MAX_ROUNDS:
                    lines = [f"**{i+1}.** {(c.get('question') or c.get('item') or str(c))}" for i, c in enumerate(new_checklist)]
                    msg = f"추가로 확인할 사항 ({cb_round + 1}차)\n\n💡 {continuation_reason or '추가 확인이 필요합니다.'}\n\n" + "\n\n".join(lines) + "\n\n각 질문에 대해 네/아니요/모르겠음 버튼을 눌러 주세요."
                    st.session_state.messages.append(AIMessage(content=msg))
                    st.session_state.cb_checklist = new_checklist
                    st.session_state.cb_checklist_answers = {}
                    st.session_state.cb_all_qa = all_qa
                    st.session_state.cb_round = cb_round + 1
                    st.session_state.cb_checklist_rag_results = step2_res.get("rag_results") or []
                else:
                    res = step3_conclusion(cb_issue, all_qa, collection=col, narrow_answers=narrow_answers if narrow_answers else None)
                    conc = res.get("conclusion", res) if isinstance(res, dict) else str(res)
                    rel = res.get("related_articles", []) if isinstance(res, dict) else []
                    tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
                    st.session_state.messages.append(AIMessage(content=f"**결론**\n\n{conc}{tail}"))
                    st.session_state.cb_checklist = []
                    st.session_state.cb_checklist_answers = {}
                    st.session_state.cb_all_qa = []
                    st.session_state.cb_round = 1
                    st.session_state.cb_checklist_rag_results = []
                st.rerun()
            except Exception:
                st.error(USER_FACING_ERROR)
        st.divider()

    # 타겟/그룹 선택 버튼 (채팅창 위)
    pending_buttons = st.session_state.get("pending_buttons", [])
    if pending_buttons and st.session_state.messages and isinstance(st.session_state.messages[-1], AIMessage):
        st.markdown("**선택하세요:**")
        n = min(len(pending_buttons), 4)
        cols = st.columns(n)
        for i, lbl in enumerate(pending_buttons[:4]):
            with cols[i]:
                if st.button(lbl[:30] + ("..." if len(lbl) > 30 else ""), key=f"grp_btn_{i}", use_container_width=True):
                    st.session_state.messages.append(HumanMessage(content=lbl))
                    st.session_state.pending_buttons = []
                    st.rerun()
        if len(pending_buttons) >= 3 and st.button("둘 다 해당 없음", key="grp_btn_none"):
            st.session_state.messages.append(HumanMessage(content="둘 다 해당 없음"))
            st.session_state.pending_buttons = []
            st.rerun()
        st.divider()

    # 사용자 입력 (채팅창)
    prompt = st.chat_input("상황을 입력하세요...")
    if prompt:
        st.session_state.messages.append(HumanMessage(content=prompt))
        st.rerun()

    # 그래프 로드 실패 시 입력/히스토리는 보이되, 응답 생성은 건너뜀
    if graph is None:
        if st.session_state.get("graph_load_error"):
            st.warning(st.session_state.graph_load_error)
        st.divider()
        st.caption("※ 모든 답변은 근로기준법 등 제공된 법령 데이터에 기반합니다.")
        return

    # 마지막 메시지가 사용자 메시지면 AI 응답 생성 (채팅 입력 또는 시나리오 버튼)
    if st.session_state.messages and isinstance(st.session_state.messages[-1], HumanMessage):
        last_human = st.session_state.messages[-1]
        with st.chat_message("assistant"):
            with st.spinner("검토 중..."):
                config = {"configurable": {"thread_id": thread_id}}
                try:
                    result = graph.invoke(
                        {"messages": [last_human]},
                        config=config,
                    )
                    new_msgs = result.get("messages", [])
                    ai_content = ""
                    for m in reversed(new_msgs):
                        if isinstance(m, AIMessage):
                            ai_content = m.content
                            break
                    if ai_content:
                        st.markdown(ai_content)
                        st.session_state.messages.append(AIMessage(content=ai_content))
                        # 체크리스트면 app.py와 동일하게 버튼으로 답하도록 상태 저장
                        if result.get("phase") == "checklist" and result.get("checklist"):
                            st.session_state.cb_checklist = result.get("checklist", [])
                            st.session_state.cb_checklist_answers = {}
                            st.session_state.cb_issue = result.get("selected_issue", "")
                            st.session_state.cb_situation = result.get("situation", "")
                            st.session_state.cb_articles_by_issue = dict(result.get("articles_by_issue") or {})
                            st.session_state.cb_round = 1
                            st.session_state.cb_all_qa = []
                            st.session_state.cb_checklist_rag_results = list(result.get("checklist_rag_results") or [])
                            st.session_state.pending_buttons = []
                        else:
                            st.session_state.pending_buttons = []
                            if result.get("phase") == "conclusion":
                                st.session_state.cb_checklist = []
                                st.session_state.cb_checklist_answers = {}
                    else:
                        st.warning("응답을 생성하지 못했습니다. 다른 표현으로 다시 말씀해 주세요.")
                        st.session_state.pending_buttons = []
                except Exception:
                    st.error(USER_FACING_ERROR)
                    st.session_state.pending_buttons = []
        st.rerun()

    st.divider()
    st.caption("※ 모든 답변은 근로기준법 등 제공된 법령 데이터에 기반합니다.")


if __name__ == "__main__":
    main()
