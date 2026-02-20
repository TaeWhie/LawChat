"""
노동법 RAG 챗봇 - LangGraph + Streamlit 챗봇 UI (실제 서비스용)
app.py와 동일: 체크리스트는 한 번에 표시하고 네/아니요/모르겠음 버튼으로 답하며, 여러 차수(라운드) 지원.
장별 둘러보기는 app.py와 동일하게 조항 클릭 시 상세 페이지 표시.
"""
import re
import time
import threading
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

# 백그라운드 처리 결과 (스레드에서 저장, 메인에서 읽기) — 타임아웃 방지
_pending_result = {}
_lock = threading.Lock()

from rag.law_json import get_laws, get_chapters, get_articles_by_chapter
from rag.store import build_vector_store, search_by_article_numbers
from config import SOURCE_LAW

CHECKLIST_MAX_ROUNDS = 3  # app.py와 동일

# 사용자에게 보여줄 고정 메시지 (기술적 오류 내용 노출 방지)
USER_FACING_ERROR = "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
LOAD_ERROR_MESSAGE = "서비스를 불러오는 중 문제가 발생했습니다. 새로고침 후 다시 시도해 주세요."
CHECKLIST_PROCESSING_MSG = "⏳ **처리 중입니다.** 잠시만 기다려 주세요."


@st.cache_data(ttl=3600)  # 1시간 캐싱
def _cached_get_laws():
    """법률 목록 캐싱"""
    try:
        return get_laws()
    except Exception:
        return []


@st.cache_data(ttl=3600)  # 1시간 캐싱
def _cached_get_chapters(law_id: str, source: str = None):
    """장 목록 캐싱"""
    try:
        return get_chapters(law_id, source)
    except Exception:
        return []


@st.cache_data(ttl=3600)  # 1시간 캐싱
def _cached_get_articles_by_chapter(chapter_number: str, law_id: str, source: str = None):
    """조문 목록 캐싱"""
    try:
        return get_articles_by_chapter(chapter_number, law_id, source) or []
    except Exception:
        return []


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
    if "cb_checklist_submitted" not in st.session_state:
        st.session_state.cb_checklist_submitted = False
    # 결론 후 관련 질문
    if "related_questions" not in st.session_state:
        st.session_state.related_questions = []
    # 법률 둘러보기
    if "browse_view" not in st.session_state:
        st.session_state.browse_view = None
    if "browse_law_id" not in st.session_state:
        st.session_state.browse_law_id = ""
    if "browse_law_name" not in st.session_state:
        st.session_state.browse_law_name = ""
    if "browse_law_source" not in st.session_state:
        st.session_state.browse_law_source = None
    if "browse_article_number" not in st.session_state:
        st.session_state.browse_article_number = None
    if "browse_chapter_title" not in st.session_state:
        st.session_state.browse_chapter_title = ""
    if "browse_article_paragraphs" not in st.session_state:
        st.session_state.browse_article_paragraphs = []
    if "browse_article_title" not in st.session_state:
        st.session_state.browse_article_title = ""


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
            st.session_state.related_questions = []
            st.session_state.messages = []
            st.session_state.pending_buttons = []
            st.session_state.graph_load_error = None
            st.session_state.cb_checklist = []
            st.session_state.cb_checklist_answers = {}
            st.session_state.cb_issue = ""
            st.session_state.cb_situation = ""
            st.session_state.cb_articles_by_issue = {}
            st.session_state.cb_round = 1
            st.session_state.cb_checklist_rag_results = []
            st.session_state.cb_checklist_submitted = False
            st.session_state.browse_view = None
            st.session_state.browse_law_id = ""
            st.session_state.browse_law_name = ""
            st.session_state.browse_law_source = None
            st.session_state.browse_article_number = None
            st.session_state.browse_chapter_title = ""
            st.session_state.browse_article_paragraphs = []
            st.session_state.browse_article_title = ""
            import uuid
            st.session_state.thread_id = str(uuid.uuid4())[:8]
            st.rerun()
        st.divider()
        st.subheader("📚 법률 둘러보기")
        laws = _cached_get_laws()  # 캐싱된 법률 목록
        for group in laws:
            group_name = group.get("group_name", "") or "법령"
            items = group.get("items") or []
            with st.expander(group_name, expanded=False):
                for item in items:
                    law_id = item.get("id", "")
                    law_name = item.get("name", "")
                    source = item.get("source")
                    with st.expander(law_name or law_id, expanded=False):
                        chapters = _cached_get_chapters(law_id, source)  # 캐싱된 장 목록
                        for ch in chapters:
                            with st.expander(f"{ch.get('number','')} {ch.get('title','')}".strip(), expanded=False):
                                articles = _cached_get_articles_by_chapter(ch["number"], law_id, source)  # 캐싱된 조문 목록
                                for i, a in enumerate(articles):
                                    art_num = a.get("article_number", "")
                                    title = a.get("title", "")
                                    paras = a.get("paragraphs") or []
                                    label = f"{art_num} {title}".strip() or art_num
                                    if st.button(label, key=f"browse_{law_id}_{ch.get('number','')}_{i}_{art_num}", use_container_width=True):
                                        st.session_state.browse_view = "article_detail"
                                        st.session_state.browse_law_id = law_id
                                        st.session_state.browse_law_name = law_name
                                        st.session_state.browse_law_source = source
                                        st.session_state.browse_article_number = art_num
                                        st.session_state.browse_chapter_title = f"{ch.get('number','')} {ch.get('title','')}".strip()
                                        st.session_state.browse_article_paragraphs = paras
                                        st.session_state.browse_article_title = title
                                        st.rerun()

    # ---------- 조항 상세 페이지 (법률 둘러보기에서 조항 클릭 시) ----------
    if st.session_state.get("browse_view") == "article_detail":
        art_num = st.session_state.get("browse_article_number") or ""
        ch_title = st.session_state.get("browse_chapter_title") or ""
        law_name = st.session_state.get("browse_law_name") or ""
        if art_num:
            paragraphs = st.session_state.get("browse_article_paragraphs") or []
            display_title = st.session_state.get("browse_article_title") or ""
            st.subheader(f"📜 {art_num} {display_title}".strip())
            if law_name:
                st.caption(f"**{law_name}**")
            if ch_title:
                st.caption(f"장: {ch_title}")
            st.divider()
            if paragraphs:
                def _strip_paragraph_text(typ: str, raw: str) -> str:
                    if not raw:
                        return raw
                    raw = raw.strip()
                    if typ == "항":
                        return re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*", "", raw)
                    if typ == "호":
                        return re.sub(r"^\d+\.\s*", "", raw)
                    if typ == "목":
                        return re.sub(r"^[가-힣]\.\s*", "", raw)
                    return raw
                prev_type = None
                for i, p in enumerate(paragraphs):
                    p_type = p.get("type", "")
                    num = p.get("num")
                    text = (p.get("text") or "").strip()
                    if not text:
                        continue
                    if prev_type == "항" and p_type not in ("호", "목"):
                        st.divider()
                    prev_type = p_type
                    display_text = _strip_paragraph_text(p_type, text)
                    if p_type == "본문":
                        st.markdown("### 본문")
                        st.markdown(display_text)
                    elif p_type == "항":
                        if num:
                            hang_num_map = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
                                            "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10"}
                            hang_num = hang_num_map.get(num, num)
                            hlabel = f"### 제{hang_num}항"
                        else:
                            hlabel = "### 항"
                        st.markdown(hlabel)
                        st.markdown(display_text)
                    elif p_type == "호":
                        label = f"-{num.rstrip('.')}호" if num else "-호"
                        st.markdown(f'<div style="margin-left: 2.5em; margin-top: 0.8em; margin-bottom: 0.3em; color: #666;">{label}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div style="margin-left: 2.5em; margin-bottom: 0.5em;">{display_text}</div>', unsafe_allow_html=True)
                    elif p_type == "목":
                        label = f"{num}목" if num else "목"
                        st.markdown(f'<div style="margin-left: 4.5em; margin-top: 0.3em; margin-bottom: 0.2em; font-size: 0.95em; color: #888;">{label}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div style="margin-left: 4.5em; font-size: 0.95em;">{display_text}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(display_text)
                if prev_type == "항":
                    st.divider()
            else:
                try:
                    col = build_vector_store()[0]
                except Exception:
                    col = None
                if col is not None:
                    docs = search_by_article_numbers(col, [art_num], SOURCE_LAW)
                    if docs:
                        r = docs[0]
                        text = (r.get("text") or "").strip()
                        chapter = r.get("chapter", "")
                        source = r.get("source", "")
                        if chapter:
                            st.caption(f"장: {chapter}")
                        if source:
                            st.caption(f"출처: {source}")
                        st.markdown(text if text else "(본문 없음)")
                    else:
                        st.warning(f"해당 조문({art_num}) 본문을 불러올 수 없습니다.")
                else:
                    st.warning("벡터 스토어를 불러올 수 없어 조문을 표시할 수 없습니다.")
        else:
            st.info("조문을 선택해 주세요.")
        st.divider()
        if st.button("← 챗봇으로 돌아가기", type="primary", key="back_to_chat_from_article"):
            st.session_state.browse_view = None
            st.session_state.browse_law_id = ""
            st.session_state.browse_law_name = ""
            st.session_state.browse_law_source = None
            st.session_state.browse_article_number = None
            st.session_state.browse_chapter_title = ""
            st.session_state.browse_article_paragraphs = []
            st.session_state.browse_article_title = ""
            st.rerun()
        return

    st.title("⚖️ 노동법 RAG 챗봇")
    st.caption("근로기준법 기반 상담. 직장에서 겪은 문제나 궁금한 점을 자유롭게 말씀해 주세요.")

    # 채팅 히스토리 표시 (체크리스트는 마지막 assistant 말풍선 안에 함께 표시)
    cb_checklist = st.session_state.get("cb_checklist") or []
    cb_answers = st.session_state.get("cb_checklist_answers") or {}
    messages = st.session_state.get("messages", [])
    
    # 메시지가 없으면 빈 리스트로 초기화
    if not isinstance(messages, list):
        st.session_state.messages = []
        messages = []
    
    for i, msg in enumerate(messages):
        if msg is None:
            continue
        # 처리 중 placeholder는 여기서 그리지 않음 → 아래 대기 블록에서 스피너로 한 번만 그림
        content = msg.content if hasattr(msg, 'content') else str(msg)
        if i == len(messages) - 1 and content == CHECKLIST_PROCESSING_MSG:
            continue
        try:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            # 처리 중 메시지일 때는 체크리스트를 붙이지 않음 (처리 중 문구만 표시)
            is_last_and_checklist = (
                i == len(messages) - 1 and isinstance(msg, AIMessage) and cb_checklist
                and (msg.content or "").strip() != CHECKLIST_PROCESSING_MSG
            )
            with st.chat_message(role):
                if content:
                    st.markdown(str(content))
                
                # 결론 메시지인 경우 조항 링크 버튼 추가
                if isinstance(msg, AIMessage) and "**결론**" in (msg.content or ""):
                    try:
                        from rag.article_linker import extract_article_citations, find_article_info
                        try:
                            col = build_vector_store()[0]
                        except Exception:
                            col = None
                        
                        if col:
                            citations = extract_article_citations(msg.content or "")
                            if citations:
                                st.markdown("**📜 관련 조항:**")
                                cols = st.columns(min(len(citations), 4))
                                for idx, (law_name, article_number) in enumerate(citations[:4]):
                                    with cols[idx % 4]:
                                        article_info = find_article_info(law_name, article_number, col)
                                        if article_info:
                                            btn_label = f"{law_name}\n{article_number}"
                                            if st.button(btn_label, key=f"article_btn_{i}_{idx}", use_container_width=True):
                                                # 조항 상세 페이지로 이동
                                                st.session_state.browse_view = "article_detail"
                                                st.session_state.browse_law_id = article_info.get("law_id", "")
                                                st.session_state.browse_law_name = law_name
                                                st.session_state.browse_law_source = article_info.get("source", "")
                                                st.session_state.browse_article_number = article_number
                                                st.session_state.browse_chapter_title = article_info.get("chapter", "")
                                                
                                                # 조항 상세 정보 가져오기 (API에서)
                                                try:
                                                    from rag.api_chapters import get_article_by_number_from_api
                                                    law_id = article_info.get("law_id", "")
                                                    source = article_info.get("source", "")
                                                    article_detail = get_article_by_number_from_api(article_number, law_id, source)
                                                    if article_detail:
                                                        st.session_state.browse_article_paragraphs = article_detail.get("paragraphs", [])
                                                        st.session_state.browse_article_title = article_detail.get("title", article_number)
                                                    else:
                                                        st.session_state.browse_article_paragraphs = []
                                                        st.session_state.browse_article_title = article_number
                                                except Exception:
                                                    st.session_state.browse_article_paragraphs = []
                                                    st.session_state.browse_article_title = article_number
                                                st.rerun()
                    except Exception:
                        pass
                
                # 체크리스트 표시 (마지막 메시지이고 체크리스트가 있을 때)
                if is_last_and_checklist:
                    cb_submitted = st.session_state.get("cb_checklist_submitted", False)
                    st.markdown("**체크리스트** (각 질문에 대해 버튼을 눌러 주세요)")
                    for j, item in enumerate(cb_checklist):
                        q = item.get("question") or item.get("item") or str(item)
                        cur = cb_answers.get(j, "").strip()
                        st.write(f"**{j+1}.** {q}")
                        c1, c2, c3, _ = st.columns([1, 1, 1, 2])
                        with c1:
                            if st.button("네", key=f"cb_btn_{j}_0", type="primary" if cur == "네" else "secondary", disabled=cb_submitted):
                                st.session_state.cb_checklist_answers[j] = "네"
                                st.rerun()
                        with c2:
                            if st.button("아니요", key=f"cb_btn_{j}_1", type="primary" if cur == "아니요" else "secondary", disabled=cb_submitted):
                                st.session_state.cb_checklist_answers[j] = "아니요"
                                st.rerun()
                        with c3:
                            if st.button("모르겠음", key=f"cb_btn_{j}_2", type="primary" if cur == "모르겠음" else "secondary", disabled=cb_submitted):
                                st.session_state.cb_checklist_answers[j] = "모르겠음"
                                st.rerun()
                    # 다음 버튼: 모든 답변이 완료되었을 때만 활성화
                    all_answered = len(cb_answers) == len(cb_checklist) and all(cb_answers.get(i, "").strip() for i in range(len(cb_checklist)))
                    if not cb_submitted:
                        st.divider()
                        if st.button("다음", type="primary", key="cb_next_btn", use_container_width=True, disabled=not all_answered):
                            st.session_state.cb_checklist_submitted = True
                            st.session_state.messages.append(AIMessage(content=CHECKLIST_PROCESSING_MSG))
                            st.rerun()
        except Exception as e:
            # 메시지 렌더링 오류 시 건너뛰기
            continue

    # 체크리스트 제출 버튼을 눌렀으면 should_continue 판단 → 2차 체크리스트 또는 결론
    cb_submitted = st.session_state.get("cb_checklist_submitted", False)
    if cb_checklist and messages and isinstance(messages[-1], AIMessage) and cb_submitted and len(cb_answers) == len(cb_checklist):
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

            # "처리 중" 메시지가 마지막이면 제거 후 결과만 추가
            if st.session_state.messages and isinstance(st.session_state.messages[-1], AIMessage) and st.session_state.messages[-1].content == CHECKLIST_PROCESSING_MSG:
                st.session_state.messages.pop()
            if should_continue and new_checklist and cb_round < CHECKLIST_MAX_ROUNDS:
                msg = f"추가로 확인할 사항 ({cb_round + 1}차)\n\n💡 {continuation_reason or '추가 확인이 필요합니다.'}\n\n아래에서 각 질문에 대해 네/아니요/모르겠음 버튼을 눌러 주세요."
                st.session_state.messages.append(AIMessage(content=msg))
                st.session_state.cb_checklist = new_checklist
                st.session_state.cb_checklist_answers = {}
                st.session_state.cb_checklist_submitted = False
                st.session_state.cb_all_qa = all_qa
                st.session_state.cb_round = cb_round + 1
                st.session_state.cb_checklist_rag_results = step2_res.get("rag_results") or []
            else:
                res = step3_conclusion(cb_issue, all_qa, collection=col, narrow_answers=narrow_answers if narrow_answers else None)
                conc = res.get("conclusion", res) if isinstance(res, dict) else str(res)
                rel = res.get("related_articles", []) if isinstance(res, dict) else []
                tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
                st.session_state.messages.append(AIMessage(content=f"**결론**\n\n{conc}{tail}"))
                
                # 결론 생성 후 관련 질문 생성
                try:
                    from rag.prompts import system_related_questions, user_related_questions
                    from rag.llm import chat_json
                    questions_result = chat_json(
                        system_related_questions(),
                        user_related_questions(conc, cb_issue),
                        max_tokens=300
                    )
                    if isinstance(questions_result, list) and len(questions_result) > 0:
                        st.session_state.related_questions = questions_result[:5]  # 최대 5개
                    else:
                        st.session_state.related_questions = []
                except Exception:
                    st.session_state.related_questions = []
                
                st.session_state.cb_checklist = []
                st.session_state.cb_checklist_answers = {}
                st.session_state.cb_checklist_submitted = False
                st.session_state.cb_all_qa = []
                st.session_state.cb_round = 1
                st.session_state.cb_checklist_rag_results = []
            st.rerun()
        except Exception:
            st.error(USER_FACING_ERROR)

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

    # 관련 질문 버튼 표시 (결론 생성 후)
    related_questions = st.session_state.get("related_questions", [])
    if related_questions:
        st.markdown("**💡 관련 질문:**")
        cols = st.columns(min(len(related_questions), 3))
        for i, question in enumerate(related_questions[:3]):  # 최대 3개만 표시
            with cols[i % 3]:
                if st.button(question, key=f"related_q_{i}", use_container_width=True):
                    st.session_state.messages.append(HumanMessage(content=question))
                    st.session_state.related_questions = []  # 질문 선택 후 제거
                    st.rerun()
        if len(related_questions) > 3:
            st.caption(f"그 외 {len(related_questions) - 3}개의 관련 질문이 있습니다. 입력창에 직접 질문해 주세요.")
    
    # 사용자 입력 (채팅창)
    # 다양한 친근한 입력 안내 문구 (랜덤 선택)
    import random
    input_placeholders = [
        "직장에서 겪은 문제를 말씀해 주세요...",
        "어떤 도움이 필요하신가요?",
        "궁금한 노동법 질문을 입력하세요...",
        "상황을 자유롭게 설명해 주세요...",
        "예: 월급을 못 받았어요, 해고당했어요...",
        "직장 관련 법적 문제를 알려주세요...",
        "무엇이 궁금하신가요?",
    ]
    # 그래프 로드 실패 시 입력/히스토리는 보이되, 응답 생성은 건너뜀
    if graph is None:
        if st.session_state.get("graph_load_error"):
            st.warning(st.session_state.graph_load_error)
        st.caption("※ 모든 답변은 근로기준법 등 제공된 법령 데이터에 기반합니다.")
        
        # 메시지 히스토리 표시 (그래프가 없어도 메시지는 표시)
        messages = st.session_state.get("messages", [])
        if not isinstance(messages, list):
            st.session_state.messages = []
            messages = []
        
        for i, msg in enumerate(messages):
            if msg is None:
                continue
            try:
                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                with st.chat_message(role):
                    content = msg.content if hasattr(msg, 'content') else str(msg)
                    if content:
                        st.markdown(str(content))
            except Exception:
                continue
        
        # 그래프가 없어도 입력은 받을 수 있도록
        placeholder = random.choice(input_placeholders)
        prompt = st.chat_input(placeholder, key="chat_input_no_graph")
        if prompt:
            if "messages" not in st.session_state:
                st.session_state.messages = []
            st.session_state.messages.append(HumanMessage(content=prompt))
            # st.chat_input()은 자동으로 rerun을 트리거하므로 명시적 rerun 불필요
            # 하지만 메시지가 즉시 표시되도록 명시적으로 rerun 호출
            st.rerun()
            return
        
        # 페이지 하단 출처 표시 및 면책 공고 (채팅창이 비어있을 때만 표시)
        if not messages or len(messages) == 0:
            st.divider()
            st.markdown("---")
            
            # 업데이트 날짜 읽기
            update_date = "알 수 없음"
            try:
                from pathlib import Path
                last_update_file = Path("api_data/last_update.txt")
                if last_update_file.exists():
                    update_date = last_update_file.read_text(encoding="utf-8").strip()
                    # UTC를 한국 시간으로 변환 (UTC+9)
                    if "UTC" in update_date:
                        from datetime import datetime, timedelta
                        try:
                            dt_str = update_date.replace(" UTC", "")
                            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                            dt_kst = dt + timedelta(hours=9)
                            update_date = dt_kst.strftime("%Y년 %m월 %d일 %H:%M")
                        except Exception:
                            pass
            except Exception:
                pass
            
            st.markdown(
                f"""
                <div style="text-align: center; color: #666; font-size: 0.85em; padding: 1em 0;">
                    <p><strong>📚 데이터 출처</strong></p>
                    <p>본 콘텐츠는 법제처 국가법령정보센터의 공공데이터를 활용하여 작성되었습니다.</p>
                    <p style="margin-top: 0.5em; color: #888; font-size: 0.9em;">마지막 업데이트: {update_date}</p>
                    <p style="margin-top: 1em;"><strong>⚠️ 면책 공고</strong></p>
                    <p>본 서비스는 AI 기반 법률 상담 챗봇으로, 제공되는 정보는 참고용이며 법적 조언을 대체하지 않습니다.</p>
                    <p>실제 법률 문제가 있는 경우 반드시 전문 법률가와 상담하시기 바랍니다.</p>
                    <p style="margin-top: 0.5em; font-size: 0.9em;">본 서비스의 정보로 인한 어떠한 손해에 대해서도 책임을 지지 않습니다.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
        return

    # AI 처리 중인지 확인 (마지막 메시지가 HumanMessage면 AI 응답 생성 필요)
    is_ai_processing = (
        st.session_state.messages and
        isinstance(st.session_state.messages[-1], HumanMessage)
    )
    # 백그라운드 처리 대기 중인지 (처리 placeholder가 마지막 메시지)
    is_processing_placeholder = (
        st.session_state.messages
        and isinstance(st.session_state.messages[-1], AIMessage)
        and st.session_state.messages[-1].content == CHECKLIST_PROCESSING_MSG
    )

    # 사용자 입력 처리 (AI 처리 중이 아닐 때만)
    if not is_ai_processing:
        placeholder = random.choice(input_placeholders)
        prompt = st.chat_input(placeholder, key="main_chat_input")
        if prompt:
            if "messages" not in st.session_state:
                st.session_state.messages = []
            st.session_state.messages.append(HumanMessage(content=prompt))
            st.session_state.related_questions = []
            st.rerun()
            return  # rerun 후 같은 run에서 AI 블록으로 넘어가지 않도록
    else:
        placeholder = random.choice(input_placeholders)
        st.chat_input(placeholder, key="main_chat_input")
        # AI 처리 중에는 입력 무시 (prompt 확인 안 함)

    # 페이지 하단 출처/면책: 채팅 비어있을 때만, 처리 중·대기 중이 아닐 때만
    _messages = st.session_state.get("messages", [])
    _show_footer = (not _messages or len(_messages) == 0) and not is_ai_processing and not is_processing_placeholder
    if _show_footer:
        st.divider()
        st.markdown("---")
        update_date = "알 수 없음"
        try:
            from pathlib import Path
            last_update_file = Path("api_data/last_update.txt")
            if last_update_file.exists():
                update_date = last_update_file.read_text(encoding="utf-8").strip()
                if "UTC" in update_date:
                    from datetime import datetime, timedelta
                    try:
                        dt_str = update_date.replace(" UTC", "")
                        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                        dt_kst = dt + timedelta(hours=9)
                        update_date = dt_kst.strftime("%Y년 %m월 %d일 %H:%M")
                    except Exception:
                        pass
        except Exception:
            pass
        st.markdown(
            f"""
            <div style="text-align: center; color: #666; font-size: 0.85em; padding: 1em 0;">
                <p><strong>📚 데이터 출처</strong></p>
                <p>본 콘텐츠는 법제처 국가법령정보센터의 공공데이터를 활용하여 작성되었습니다.</p>
                <p style="margin-top: 0.5em; color: #888; font-size: 0.9em;">마지막 업데이트: {update_date}</p>
                <p style="margin-top: 1em;"><strong>⚠️ 면책 공고</strong></p>
                <p>본 서비스는 AI 기반 법률 상담 챗봇으로, 제공되는 정보는 참고용이며 법적 조언을 대체하지 않습니다.</p>
                <p>실제 법률 문제가 있는 경우 반드시 전문 법률가와 상담하시기 바랍니다.</p>
                <p style="margin-top: 0.5em; font-size: 0.9em;">본 서비스의 정보로 인한 어떠한 손해에 대해서도 책임을 지지 않습니다.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    request_id = st.session_state.get("_processing_request_id")

    def _run_invoke(req_id, last_human_msg, config_dict):
        try:
            r = graph.invoke({"messages": [last_human_msg]}, config=config_dict)
            with _lock:
                _pending_result[req_id] = ("ok", r)
        except Exception as e:
            with _lock:
                _pending_result[req_id] = ("error", str(e))

    # 1) 방금 사용자 메시지가 들어왔을 때: 처리 placeholder 추가 후 백그라운드 스레드 시작
    if is_ai_processing:
        last_human = st.session_state.messages[-1]
        import uuid
        req_id = str(uuid.uuid4())[:12]
        st.session_state.messages.append(AIMessage(content=CHECKLIST_PROCESSING_MSG))
        st.session_state._processing_request_id = req_id
        t = threading.Thread(
            target=_run_invoke,
            args=(req_id, last_human, {"configurable": {"thread_id": thread_id}}),
            daemon=True,
        )
        t.start()
        st.rerun()
        return

    # 2) 백그라운드 처리 대기 중: 결과 있으면 반영, 없으면 짧게 대기 후 재실행 (타임아웃 방지)
    if is_processing_placeholder and request_id:
        with _lock:
            res = _pending_result.pop(request_id, None)
        if res is not None:
            status, data = res
            # placeholder 제거
            if st.session_state.messages and isinstance(st.session_state.messages[-1], AIMessage):
                if st.session_state.messages[-1].content == CHECKLIST_PROCESSING_MSG:
                    st.session_state.messages.pop()
            st.session_state._processing_request_id = None
            if status == "error":
                st.session_state.messages.append(AIMessage(content=USER_FACING_ERROR))
                st.session_state.pending_buttons = []
            else:
                result = data
                new_msgs = result.get("messages", [])
                ai_content = ""
                for m in reversed(new_msgs):
                    if isinstance(m, AIMessage):
                        ai_content = m.content
                        break
                if ai_content:
                    st.session_state.messages.append(AIMessage(content=ai_content))
                    if result.get("phase") == "checklist" and result.get("checklist"):
                        st.session_state.cb_checklist = result.get("checklist", [])
                        st.session_state.cb_checklist_answers = {}
                        st.session_state.cb_checklist_submitted = False
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
                            conclusion_content = ""
                            for msg in reversed(new_msgs):
                                if isinstance(msg, AIMessage) and "결론" in (msg.content or ""):
                                    conclusion_content = msg.content
                                    break
                            try:
                                from rag.prompts import system_related_questions, user_related_questions
                                from rag.llm import chat_json
                                issue = result.get("selected_issue", "")
                                if conclusion_content and issue:
                                    qr = chat_json(
                                        system_related_questions(),
                                        user_related_questions(conclusion_content, issue),
                                        max_tokens=300,
                                    )
                                    st.session_state.related_questions = (qr[:5] if isinstance(qr, list) and qr else [])
                                else:
                                    st.session_state.related_questions = []
                            except Exception:
                                st.session_state.related_questions = []
                            st.session_state.cb_checklist = []
                            st.session_state.cb_checklist_answers = {}
                            st.session_state.cb_checklist_submitted = False
                else:
                    st.session_state.messages.append(AIMessage(content="응답을 생성하지 못했습니다. 다른 표현으로 다시 말씀해 주세요."))
                    st.session_state.pending_buttons = []
            st.rerun()
            return
        # 결과 아직 없음: 스피너로 표시하고 짧게 대기 후 재실행 (run 타임아웃 방지)
        with st.chat_message("assistant"):
            with st.spinner("처리 중입니다. 잠시만 기다려 주세요."):
                time.sleep(2)
        st.rerun()
        return


if __name__ == "__main__":
    main()
