"""
노동법 RAG 챗봇 - LangGraph + Streamlit 챗봇 UI (실제 서비스용)
대화형 메시지 형식으로 상담 진행
"""
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from rag.law_json import SCENARIO_QUICK, get_chapters, get_articles_by_chapter

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
                        # 타겟 단계: 해당함/해당 없음 버튼
                        if result.get("phase") == "target":
                            st.session_state.pending_buttons = ["해당함", "해당 없음"]
                        else:
                            st.session_state.pending_buttons = []
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
