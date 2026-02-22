"""
노동법 RAG 챗봇 - LangGraph + Streamlit 챗봇 UI (실제 서비스용)
app.py와 동일: 체크리스트는 한 번에 표시하고 네/아니요/모르겠음 버튼으로 답하며, 여러 차수(라운드) 지원.
장별 둘러보기는 app.py와 동일하게 조항 클릭 시 상세 페이지 표시.

[화면 전환 최적화]
- @st.cache_resource: 그래프(_cached_get_graph), 벡터 스토어(_cached_vector_store) 한 번만 로드.
- @st.cache_data(ttl=3600): 법률 목록/장/조문(_cached_get_laws 등) 1시간 캐싱.
- on_click 콜백: 새 대화, 돌아가기, 체크리스트, 다음, 관련 질문, 타겟 선택.
- 법률 둘러보기: 버튼 없이 사이드바에 트리만 표시. 사이드바는 streamlit-browser-session-storage로 브라우저와 동기화.
- 조항 상세 보기 시 사이드바 경량화: article_detail일 때 법률 트리 미로드, "← 채팅으로"만 표시.
- 채팅 placeholder 세션 고정, footer 업데이트 날짜 @st.cache_data(ttl=60).
- 채팅 영역 @st.fragment: 체크리스트/입력 시 해당 부분만 리런되어 속도 개선 (Streamlit 1.33+).
"""
import re
import time
import threading
import json
import os
import tempfile
from pathlib import Path
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

def _safe_fragment_rerun():
    """fragment 스코프 rerun을 시도하고, 전체 앱 rerun 컨텍스트라 실패하면 전체 rerun으로 폴백."""
    try:
        from streamlit.errors import StreamlitAPIException
        st.rerun(scope="fragment")
    except Exception:
        st.rerun()

try:
    from streamlit_session_browser_storage import SessionStorage
except ImportError:
    SessionStorage = None  # optional: streamlit-browser-session-storage

# 백그라운드 처리 결과 (스레드에서 저장, 메인에서 읽기) — 타임아웃 방지
_pending_result = {}
_lock = threading.Lock()

# 멀티 워커 시 프로세스 간 결과 공유: 배포(Streamlit Cloud 등)에서 temp 디렉터리가 워커별로 다를 수 있으므로 프로젝트 루트 기준 사용
_APP_DIR = Path(__file__).resolve().parent
_PENDING_DIR = _APP_DIR / ".streamlit_pending"

def _pending_path(req_id: str):
    return _PENDING_DIR / f"{req_id}.json"


def _json_safe(obj):
    """JSON 직렬화 가능한 형태로 재귀 변환 (복잡한 객체는 제거/문자열화)"""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return str(obj)


def _serialize_ok_result(r):
    """graph.invoke() 결과를 JSON 직렬화 가능한 dict로 변환"""
    msgs = r.get("messages") or []
    msg_list = []
    for m in msgs:
        c = getattr(m, "content", None) or str(m)
        kind = "AIMessage" if isinstance(m, AIMessage) else "HumanMessage"
        msg_list.append({"t": kind, "c": c})
    raw = {
        "status": "ok",
        "messages": msg_list,
        "phase": r.get("phase"),
        "checklist": r.get("checklist"),
        "selected_issue": r.get("selected_issue"),
        "situation": r.get("situation"),
        "articles_by_issue": r.get("articles_by_issue"),
        "checklist_rag_results": r.get("checklist_rag_results"),
    }
    return _json_safe(raw)


def _deserialize_result(data: dict):
    """파일에서 읽은 JSON을 (status, data) 형태로 복원. data는 기존 result와 동일한 형태."""
    status = data.get("status", "ok")
    if status == "error":
        return ("error", data.get("error", ""))
    msg_list = data.get("messages") or []
    new_msgs = []
    for x in msg_list:
        if x.get("t") == "AIMessage":
            new_msgs.append(AIMessage(content=x.get("c") or ""))
        else:
            new_msgs.append(HumanMessage(content=x.get("c") or ""))
    result = {
        "messages": new_msgs,
        "phase": data.get("phase"),
        "checklist": data.get("checklist"),
        "selected_issue": data.get("selected_issue"),
        "situation": data.get("situation"),
        "articles_by_issue": data.get("articles_by_issue"),
        "checklist_rag_results": data.get("checklist_rag_results"),
    }
    return ("ok", result)


from rag.law_json import get_laws, get_chapters, get_articles_by_chapter
from rag.store import build_vector_store, search_by_article_numbers
from config import SOURCE_LAW

CHECKLIST_MAX_ROUNDS = 3  # app.py와 동일

# 사용자에게 보여줄 고정 메시지 (기술적 오류 내용 노출 방지)
USER_FACING_ERROR = "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
LOAD_ERROR_MESSAGE = "서비스를 불러오는 중 문제가 발생했습니다. 새로고침 후 다시 시도해 주세요."
CHECKLIST_PROCESSING_MSG = "⏳ **처리 중입니다.** 잠시만 기다려 주세요."

# 예시 질문 (초기 빈 화면 안내용)
EXAMPLE_QUESTIONS = [
    "월급을 제때 못 받았어요",
    "갑자기 해고 통보를 받았어요",
    "연장근무 수당을 못 받았어요",
    "육아휴직을 거부당했어요",
    "최저임금보다 적게 받고 있어요",
    "부당한 징계를 받았어요",
]


@st.cache_data(ttl=3600)  # 1시간 캐싱
def _cached_get_laws_v11():
    """법률 목록 캐싱 및 2차 필터링 (동기화 보장용)"""
    try:
        from config import ALL_LABOR_LAW_SOURCES
        allowed = set(s.split("(")[0].strip().replace("ㆍ", "·") for s in ALL_LABOR_LAW_SOURCES if s)
        
        laws = get_laws() # rag.law_json.get_laws -> rag.api_chapters.get_laws_from_api
        
        # 2차 필터링: 만약 backend(api_chapters)에서 필터링이 실패하더라도 UI에서 차단
        filtered = []
        for group in laws:
            g_name = (group.get("group_name") or "").replace("ㆍ", "·")
            if g_name in allowed:
                filtered.append(group)
        return filtered
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


@st.cache_resource
def _cached_get_graph():
    """그래프·벡터스토어는 한 번만 생성 (화면 전환 시 재실행 방지)."""
    try:
        from rag.graph import get_graph
        return get_graph()
    except Exception:
        return None


@st.cache_resource
def _cached_vector_store():
    """벡터 스토어 컬렉션 한 번만 로드 (조문 검색/결론 시 반복 로드 방지).
    graph._collection_cache도 동시에 채워 두 경로에서 build_vector_store()가
    중복 실행되지 않도록 한다.
    """
    try:
        col, _ = build_vector_store()
        # graph.py _get_collection() 캐시 공유 → 중복 build 방지
        try:
            import rag.graph as _g
            if _g._collection_cache is None:
                _g._collection_cache = col
        except Exception:
            pass
        return col
    except Exception:
        return None


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
    if "chat_placeholder" not in st.session_state:
        st.session_state.chat_placeholder = None
    # 새 대화 확인 다이얼로그 상태
    if "confirm_new_chat" not in st.session_state:
        st.session_state.confirm_new_chat = False
    # AI 처리 단계 표시용
    if "processing_step" not in st.session_state:
        st.session_state.processing_step = 0
    # 백그라운드 처리 결과 도착 알림 (법률 탐색 중 결과 준비됐을 때 뱃지 표시)
    if "_result_just_arrived" not in st.session_state:
        st.session_state._result_just_arrived = False
    
    # ── 캐시 초기화 (필터링 로직 변경 반영용 - 1회성) ──────────────────────
    if "_laws_filter_cleared_v10" not in st.session_state:
        st.cache_data.clear()
        st.session_state._laws_filter_cleared_v10 = True

def get_graph_safe():
    """그래프 로드. 실패 시 None 반환하고 session_state.graph_load_error에 메시지 저장."""
    if st.session_state.get("graph_load_error"):
        return None
    try:
        g = _cached_get_graph()
        if g is None:
            st.session_state.graph_load_error = LOAD_ERROR_MESSAGE
        return g
    except Exception:
        st.session_state.graph_load_error = LOAD_ERROR_MESSAGE
        return None


def _on_new_chat():
    """새 대화 시작 버튼 콜백: 세션 초기화. 버튼 클릭 후 Streamlit이 자동 rerun하므로 여기서 rerun 호출 안 함."""
    import uuid
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
    st.session_state.thread_id = str(uuid.uuid4())[:8]
    st.session_state.chat_placeholder = None
    st.session_state.confirm_new_chat = False
    st.session_state.processing_step = 0


def _on_confirm_new_chat():
    """새 대화 확인 버튼 콜백."""
    _on_new_chat()


def _on_cancel_new_chat():
    """새 대화 취소 콜백."""
    st.session_state.confirm_new_chat = False


def _on_request_new_chat():
    """새 대화 시작 버튼 콜백: 메시지가 있으면 확인 화면으로, 없으면 바로 실행."""
    if st.session_state.get("messages"):
        st.session_state.confirm_new_chat = True
    else:
        _on_new_chat()


def _on_back_to_chat():
    """채팅으로 돌아가기 버튼 콜백. 챗봇 화면으로 돌아오면 사이드바 닫기."""
    st.session_state.browse_view = None
    st.session_state.browse_law_id = ""
    st.session_state.browse_law_name = ""
    st.session_state.browse_law_source = None
    st.session_state.browse_article_number = None
    st.session_state.browse_chapter_title = ""
    st.session_state.browse_article_paragraphs = []
    st.session_state.browse_article_title = ""


def _make_checklist_cb(idx: int, answer: str):
    """체크리스트 네/아니요/모르겠음 버튼용 콜백 — fragment 내에서 부분 리런."""
    def _():
        st.session_state.cb_checklist_answers[idx] = answer
        # fragment 내부에서 호출 시 채팅 영역만 리런 (scope 인자 없으면 fragment 기본 동작)
        # st.rerun() 제거: 콜백 함수 내에서는 자동으로 리런됨
    return _


def _on_checklist_next():
    """체크리스트 '다음' 버튼 콜백 — fragment 내에서 부분 리런."""
    st.session_state.cb_checklist_submitted = True
    st.session_state.messages.append(AIMessage(content=CHECKLIST_PROCESSING_MSG))


def _make_related_q_cb(question: str):
    """관련 질문 버튼용 콜백 — fragment 내에서 부분 리런."""
    def _():
        st.session_state.messages.append(HumanMessage(content=question))
        st.session_state.related_questions = []
    return _


def _make_pending_btn_cb(label: str):
    """타겟/그룹 선택 버튼용 콜백 — fragment 내에서 부분 리런."""
    def _():
        st.session_state.messages.append(HumanMessage(content=label))
        st.session_state.pending_buttons = []
    return _


def _on_pending_none():
    """'둘 다 해당 없음' 버튼 콜백 — fragment 내에서 부분 리런."""
    st.session_state.messages.append(HumanMessage(content="둘 다 해당 없음"))
    st.session_state.pending_buttons = []


@st.cache_data(ttl=60)
def _cached_update_date():
    """footer용 업데이트 날짜 (60초 캐시)."""
    try:
        from pathlib import Path
        from datetime import datetime, timedelta
        p = Path("api_data/last_update.txt")
        if not p.exists():
            return "알 수 없음"
        s = p.read_text(encoding="utf-8").strip()
        if "UTC" in s:
            try:
                dt = datetime.strptime(s.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
                s = (dt + timedelta(hours=9)).strftime("%Y년 %m월 %d일 %H:%M")
            except Exception:
                pass
        return s
    except Exception:
        return "알 수 없음"


def _render_footer():
    """페이지 하단 출처/면책 공고. 한 곳에서만 호출."""
    update_date = _cached_update_date()
    st.divider()
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


def _render_welcome_screen():
    """초기 빈 화면: 환영 메시지 + 예시 질문 버튼."""
    st.markdown(
        """
        <div style="text-align:center; padding: 2em 0 1.5em 0;">
            <div style="font-size:3em;">⚖️</div>
            <h2 style="margin: 0.3em 0 0.2em 0;">노동법 RAG 챗봇</h2>
            <p style="color:#555; font-size:1.05em;">근로기준법 등 <strong>11개 노동 법령</strong>을 기반으로 상담해 드립니다.</p>
            <p style="color:#888; font-size:0.9em;">AI 답변은 참고용이며 법적 조언을 대체하지 않습니다.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("**💬 이런 상황을 도와드릴 수 있어요**")
    cols = st.columns(2)
    for idx, q in enumerate(EXAMPLE_QUESTIONS):
        with cols[idx % 2]:
            if st.button(q, key=f"example_q_{idx}", use_container_width=True):
                st.session_state.messages.append(HumanMessage(content=q))
                st.session_state.related_questions = []
                _safe_fragment_rerun()
    st.markdown("")
    st.info("💡 위 예시 외에도 직장에서 겪은 문제를 **아래 입력창에 자유롭게 입력**하시면 됩니다.", icon=None)


# ─────────────────────────────────────────────────────────────────────────────
# @st.fragment: 채팅 영역만 부분 리런
# - 체크리스트 버튼(네/아니요/모르겠음), 관련 질문, 처리 중 폴링 → fragment 내 st.rerun() → 채팅 영역만 갱신
# - 조항 상세 이동(article_btn), 예시 질문 → st.rerun(scope="app") → 전체 앱 갱신
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment
def _render_chat_ui():
        graph = get_graph_safe()
        thread_id = st.session_state.thread_id
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
                            col = _cached_vector_store()
                            if col:
                                citations = extract_article_citations(msg.content or "")
                                if citations:
                                    st.markdown("**📜 관련 조항:**")
                                    n_cols = min(len(citations), 4)
                                    valid_citations = []
                                    for law_name, article_number in citations[:4]:
                                        article_info = find_article_info(law_name, article_number, col)
                                        if article_info:
                                            valid_citations.append((law_name, article_number, article_info))
                                    if valid_citations:
                                        btn_cols = st.columns(min(len(valid_citations), 4))
                                        for idx, (law_name, article_number, article_info) in enumerate(valid_citations):
                                            with btn_cols[idx]:
                                                # 법령명 줄이기 (괄호 이후 제거)
                                                short_law = law_name.split("(")[0] if "(" in law_name else law_name
                                                btn_label = f"{short_law}\n{article_number}"
                                                if st.button(btn_label, key=f"article_btn_{i}_{idx}", use_container_width=True):
                                                    st.session_state.browse_view = "article_detail"
                                                    st.session_state.browse_law_id = article_info.get("law_id", "")
                                                    st.session_state.browse_law_name = law_name
                                                    st.session_state.browse_law_source = article_info.get("source", "")
                                                    st.session_state.browse_article_number = article_number
                                                    st.session_state.browse_chapter_title = article_info.get("chapter", "")
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
                                                    # 조항 상세 페이지로 전환: fragment 밖 layout 변경 → 전체 앱 리런
                                                    st.rerun(scope="app")
                        except Exception:
                            pass
                    
                    # 체크리스트 표시 (마지막 메시지이고 체크리스트가 있을 때)
                    if is_last_and_checklist:
                        cb_submitted = st.session_state.get("cb_checklist_submitted", False)
                        total = len(cb_checklist)
                        answered_count = sum(1 for k in range(total) if cb_answers.get(k, "").strip())
                        # 진행 상황 안내
                        st.markdown(f"**📋 체크리스트** — 각 질문에 버튼으로 답해주세요 ({answered_count}/{total} 완료)")
                        if answered_count < total and not cb_submitted:
                            st.progress(answered_count / total)
                        for j, item in enumerate(cb_checklist):
                            q = item.get("question") or item.get("item") or str(item)
                            cur = cb_answers.get(j, "").strip()
                            is_unanswered = not cur
                            # 미답변 항목은 배경 강조
                            if is_unanswered and not cb_submitted:
                                st.markdown(
                                    f'<div style="background:#fff8e1; border-left:3px solid #f9a825; '
                                    f'padding:0.4em 0.8em; border-radius:4px; margin:0.5em 0;">'
                                    f'<strong>{j+1}.</strong> {q}</div>',
                                    unsafe_allow_html=True
                                )
                            else:
                                answered_icon = {"네": "✅", "아니요": "❌", "모르겠음": "❓"}.get(cur, "")
                                st.markdown(
                                    f'<div style="padding:0.4em 0.8em; margin:0.5em 0;">'
                                    f'<strong>{j+1}.</strong> {q} {answered_icon}</div>',
                                    unsafe_allow_html=True
                                )
                            c1, c2, c3, _ = st.columns([1, 1, 1, 2])
                            with c1:
                                st.button("네", key=f"cb_btn_{j}_0", type="primary" if cur == "네" else "secondary", disabled=cb_submitted, on_click=_make_checklist_cb(j, "네"))
                            with c2:
                                st.button("아니요", key=f"cb_btn_{j}_1", type="primary" if cur == "아니요" else "secondary", disabled=cb_submitted, on_click=_make_checklist_cb(j, "아니요"))
                            with c3:
                                st.button("모르겠음", key=f"cb_btn_{j}_2", type="primary" if cur == "모르겠음" else "secondary", disabled=cb_submitted, on_click=_make_checklist_cb(j, "모르겠음"))
                        # 다음 버튼: 모든 답변이 완료되었을 때만 활성화
                        all_answered = answered_count == total
                        if not cb_submitted:
                            st.divider()
                            if not all_answered:
                                remaining = total - answered_count
                                st.caption(f"⬆️ 아직 {remaining}개 질문에 답변이 필요합니다.")
                            st.button(
                                "다음 →" if all_answered else f"다음 ({answered_count}/{total} 완료)",
                                type="primary", key="cb_next_btn",
                                use_container_width=True,
                                disabled=not all_answered,
                                on_click=_on_checklist_next
                            )
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
                from rag.store import search
                from rag.pipeline import step2_checklist, step3_conclusion
                from config import ALL_LABOR_LAW_SOURCES
                col = _cached_vector_store()
                if not col:
                    st.session_state.messages.append(AIMessage(content=USER_FACING_ERROR))
                    _safe_fragment_rerun()
                    return
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
                    # ── 결론: 스트리밍으로 실시간 표시 ──────────────────────
                    from rag.pipeline import step3_conclusion_stream
                    # "처리 중" 메시지 제거
                    if st.session_state.messages and isinstance(st.session_state.messages[-1], AIMessage) and st.session_state.messages[-1].content == CHECKLIST_PROCESSING_MSG:
                        st.session_state.messages.pop()

                    with st.chat_message("assistant"):
                        stream = step3_conclusion_stream(
                            cb_issue, all_qa,
                            collection=col,
                            narrow_answers=narrow_answers if narrow_answers else None,
                        )
                        conclusion_text = st.write_stream(stream)

                    conc = conclusion_text or ""
                    # 관련 조문 힌트는 결론 텍스트에서 추출
                    rel = re.findall(r"제\d+(?:의\d+)?조", conc)[:5]
                    tail = "\n\n📎 함께 확인해 보세요: " + ", ".join(rel) if rel else ""
                    st.session_state.messages.append(AIMessage(content=f"**결론**\n\n{conc}{tail}"))
                    
                    # 결론 생성 후 관련 질문 생성 (답변 가능한 유형만: 정보·계산·상황)
                    try:
                        from rag.prompts import system_related_questions, user_related_questions
                        from rag.llm import chat_json_fast
                        from rag.capabilities import get_related_question_capabilities, ALLOWED_RELATED_QUESTION_TYPES
                        from rag.question_classifier import classify_question_type
                        caps = get_related_question_capabilities()
                        questions_result = chat_json_fast(
                            system_related_questions(caps),
                            user_related_questions(conc, cb_issue, caps),
                            max_tokens=300
                        )
                        if isinstance(questions_result, list) and questions_result:
                            filtered = [q for q in questions_result if isinstance(q, str) and classify_question_type(q) in ALLOWED_RELATED_QUESTION_TYPES]
                            st.session_state.related_questions = filtered[:5]
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
                _safe_fragment_rerun()
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
                    st.button(lbl[:30] + ("..." if len(lbl) > 30 else ""), key=f"grp_btn_{i}", use_container_width=True, on_click=_make_pending_btn_cb(lbl))
            if len(pending_buttons) >= 2:
                st.button("둘 다 해당 없음", key="grp_btn_none", on_click=_on_pending_none)
    
        # 관련 질문 버튼 표시 (결론 생성 후) — 채팅 말풍선 아래, 입력창 위
        related_questions = st.session_state.get("related_questions", [])
        if related_questions:
            with st.container():
                st.markdown(
                    '<div style="background:#f0f4ff; border-radius:8px; padding:0.8em 1em 0.4em 1em; margin-bottom:0.5em;">',
                    unsafe_allow_html=True
                )
                st.markdown("**💡 이런 것도 궁금하지 않으신가요?**")
                q_cols = st.columns(min(len(related_questions[:3]), 3))
                for i, question in enumerate(related_questions[:3]):
                    with q_cols[i]:
                        st.button(question, key=f"related_q_{i}", use_container_width=True, on_click=_make_related_q_cb(question))
                if len(related_questions) > 3:
                    st.caption(f"그 외 {len(related_questions) - 3}개의 관련 질문이 있습니다. 입력창에 직접 질문해 주세요.")
                st.markdown('</div>', unsafe_allow_html=True)
        
        # 사용자 입력 (채팅창) — placeholder는 세션당 한 번만 선택 (리런 시 흔들림 방지)
        import random
        if st.session_state.chat_placeholder is None:
            st.session_state.chat_placeholder = random.choice([
            "직장에서 겪은 문제를 말씀해 주세요...",
            "어떤 도움이 필요하신가요?",
            "궁금한 노동법 질문을 입력하세요...",
            "상황을 자유롭게 설명해 주세요...",
            "예: 월급을 못 받았어요, 해고당했어요...",
            "직장 관련 법적 문제를 알려주세요...",
            "무엇이 궁금하신가요?",
            ])
        _placeholder = st.session_state.chat_placeholder or "직장에서 겪은 문제를 말씀해 주세요..."
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
            prompt = st.chat_input(_placeholder, key="chat_input_no_graph")
            if prompt:
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append(HumanMessage(content=prompt))
                _safe_fragment_rerun()
                return
            
            # 채팅이 비어있을 때: 환영 화면 + footer
            if not messages or len(messages) == 0:
                _render_welcome_screen()
                _render_footer()
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
            prompt = st.chat_input(_placeholder, key="main_chat_input")
            if prompt:
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                st.session_state.messages.append(HumanMessage(content=prompt))
                st.session_state.related_questions = []
                # @st.fragment 안에서 chat_input 제출 → Streamlit이 자동으로 fragment만 재실행
                # 별도 st.rerun() 불필요 — 코드가 그대로 아래로 흘러 AI 처리 블록에 진입
        else:
            st.chat_input(_placeholder, key="main_chat_input", disabled=False)
            # AI 처리 중에는 입력 무시 (prompt 확인 안 함)
    
        # 페이지 하단 출처/면책: 채팅 비어있을 때만, 처리 중·대기 중이 아닐 때만
        _messages = st.session_state.get("messages", [])
        _show_welcome = (not _messages or len(_messages) == 0) and not is_ai_processing and not is_processing_placeholder
        if _show_welcome:
            _render_welcome_screen()
            _render_footer()
    
        request_id = st.session_state.get("_processing_request_id")
    
        def _run_invoke(req_id, last_human_msg, config_dict):
            try:
                r = graph.invoke({"messages": [last_human_msg]}, config=config_dict)
                with _lock:
                    _pending_result[req_id] = ("ok", r)
                # 멀티 워커 시 다른 프로세스에서 폴링할 수 있으므로 파일에도 기록
                try:
                    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
                    p = _pending_path(req_id)
                    tmp = p.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps(_serialize_ok_result(r), ensure_ascii=False), encoding="utf-8")
                    tmp.replace(p)
                except Exception:
                    pass
            except Exception as e:
                with _lock:
                    _pending_result[req_id] = ("error", str(e))
                try:
                    _PENDING_DIR.mkdir(parents=True, exist_ok=True)
                    p = _pending_path(req_id)
                    tmp = p.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(p)
                except Exception:
                    pass
    
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
            _safe_fragment_rerun()
            return
    
        # 2) 백그라운드 처리 대기 중: 결과 있으면 반영, 없으면 짧게 대기 후 재실행 (타임아웃 방지)
        if is_processing_placeholder and request_id:
            with _lock:
                res = _pending_result.pop(request_id, None)
            # 멀티 워커: 다른 프로세스에서 스레드가 끝났을 수 있음 → 파일에서 확인
            if res is None:
                p = _pending_path(request_id)
                for _ in range(15):  # 배포 환경에서 스레드 쓰기 지연 대비 (최대 약 4.5초 대기)
                    if _PENDING_DIR.exists() and p.exists():
                        try:
                            data = json.loads(p.read_text(encoding="utf-8"))
                            res = _deserialize_result(data)
                            p.unlink(missing_ok=True)
                            break
                        except Exception:
                            pass
                    time.sleep(0.3)
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
                                    from rag.llm import chat_json_fast
                                    from rag.capabilities import get_related_question_capabilities, ALLOWED_RELATED_QUESTION_TYPES
                                    from rag.question_classifier import classify_question_type
                                    issue = result.get("selected_issue", "")
                                    if conclusion_content and issue:
                                        caps = get_related_question_capabilities()
                                        qr = chat_json_fast(
                                            system_related_questions(caps),
                                            user_related_questions(conclusion_content, issue, caps),
                                            max_tokens=300,
                                        )
                                        if isinstance(qr, list) and qr:
                                            filtered = [q for q in qr if isinstance(q, str) and classify_question_type(q) in ALLOWED_RELATED_QUESTION_TYPES]
                                            st.session_state.related_questions = filtered[:5]
                                        else:
                                            st.session_state.related_questions = []
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
                st.rerun(scope="app")  # 결과 반영 → 전체 앱 갱신으로 채팅에 답변 표시
                return
            # 결과 아직 없음: 단계 표시 스피너 + 짧게 대기 후 재실행
            # fragment 안에서 st.rerun() → 채팅 영역만 반복 폴링 (사이드바 영향 없음)
            st.session_state.processing_step = (st.session_state.get("processing_step", 0) + 1) % 4
            step = st.session_state.processing_step
            step_messages = [
                "🔍 상황을 분석하고 관련 법령을 검색하고 있습니다...",
                "📋 이슈를 분류하고 체크리스트를 생성하고 있습니다...",
                "⚖️ 법령 조문을 검토하고 결론을 작성하고 있습니다...",
                "✍️ 답변을 정리하고 있습니다...",
            ]
            with st.chat_message("assistant"):
                with st.spinner(step_messages[step]):
                    time.sleep(1)
            _safe_fragment_rerun()  # fragment 내 폴링 → 채팅 영역만 재실행


def _render_sidebar():
    with st.sidebar:
        st.markdown("### ⚖️ 노동법 챗봇")

        # ── 백그라운드 처리 중 알림 ──────────────────────────────────────
        _sb_req_id = st.session_state.get("_processing_request_id")
        _sb_msgs   = st.session_state.get("messages") or []
        _sb_last   = _sb_msgs[-1] if _sb_msgs else None
        _sb_processing = (
            _sb_req_id
            and isinstance(_sb_last, AIMessage)
            and getattr(_sb_last, "content", "") == CHECKLIST_PROCESSING_MSG
        )
        if _sb_processing:
            st.info("⏳ 답변을 생성하고 있습니다...\n\n법률을 자유롭게 둘러보세요. 완료되면 자동으로 표시됩니다.", icon=None)
            st.divider()

        # 에러 표시
        if st.session_state.get("graph_load_error"):
            st.error(st.session_state.graph_load_error)

        # 새 대화 시작 버튼 + 확인 다이얼로그
        if st.session_state.get("confirm_new_chat", False):
            st.warning("현재 대화 내용이 모두 삭제됩니다.\n\n정말 새 대화를 시작하시겠습니까?")
            c1, c2 = st.columns(2)
            with c1:
                st.button("✅ 확인", key="confirm_new_chat_yes", type="primary",
                          use_container_width=True, on_click=_on_confirm_new_chat)
            with c2:
                st.button("❌ 취소", key="confirm_new_chat_no",
                          use_container_width=True, on_click=_on_cancel_new_chat)
        else:
            st.button("🔄 새 대화 시작", on_click=_on_request_new_chat, use_container_width=True)

        st.divider()

        # 법률 둘러보기: 버튼 없이 트리만 표시
        st.markdown("**📚 법률 둘러보기**")
        st.caption("조항을 클릭하면 상세 내용을 볼 수 있습니다.")
        laws = _cached_get_laws_v11()
        for group in laws:
                group_name = group.get("group_name", "") or "법령"
                items = group.get("items") or []
                with st.expander(group_name, expanded=False):
                    for item in items:
                        law_id = item.get("id", "")
                        law_name = item.get("name", "")
                        source = item.get("source")
                        with st.expander(law_name or law_id, expanded=False):
                            chapters = _cached_get_chapters(law_id, source)
                            for ch in chapters:
                                with st.expander(f"{ch.get('number','')} {ch.get('title','')}".strip(), expanded=False):
                                    articles = _cached_get_articles_by_chapter(ch["number"], law_id, source)
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
                                            # 사이드바에서 조항 클릭: 전체 앱 리런 (조항 상세 페이지로 레이아웃 전환)
                                            st.rerun(scope="app")



def main():
    st.set_page_config(
        page_title="노동법 챗봇", layout="wide",
        initial_sidebar_state="expanded"
    )
    init_session()

    # ── 백그라운드 결과 자동 픽업 ──────────────────────────────────────────
    # fragment/사이드바 어느 쪽에서 rerun이 와도 main() 첫머리에서 결과 파일을 확인.
    # 사용자가 법률 탐색 중에도 백그라운드 스레드는 계속 실행되고, 결과 파일을 씀.
    # 돌아왔을 때 이 블록이 결과를 session_state에 반영 → 채팅 영역에 자동 표시.
    _req_id = st.session_state.get("_processing_request_id")
    _last_msg = (st.session_state.get("messages") or [None])[-1]
    _still_pending = (
        _req_id
        and isinstance(_last_msg, AIMessage)
        and getattr(_last_msg, "content", "") == CHECKLIST_PROCESSING_MSG
    )
    if _still_pending:
        # 1) 메모리에서 먼저 확인
        with _lock:
            _bg_res = _pending_result.pop(_req_id, None)
        # 2) 파일에서 확인 (멀티워커 대비, 즉시 1회만)
        if _bg_res is None:
            _p = _pending_path(_req_id)
            if _PENDING_DIR.exists() and _p.exists():
                try:
                    _bg_res = _deserialize_result(json.loads(_p.read_text(encoding="utf-8")))
                    _p.unlink(missing_ok=True)
                except Exception:
                    _bg_res = None
        if _bg_res is not None:
            _bg_status, _bg_data = _bg_res
            # placeholder 제거
            if (st.session_state.messages
                    and isinstance(st.session_state.messages[-1], AIMessage)
                    and st.session_state.messages[-1].content == CHECKLIST_PROCESSING_MSG):
                st.session_state.messages.pop()
            st.session_state._processing_request_id = None
            if _bg_status == "error":
                st.session_state.messages.append(AIMessage(content=USER_FACING_ERROR))
                st.session_state.pending_buttons = []
            else:
                _bg_result = _bg_data
                _bg_new_msgs = _bg_result.get("messages", [])
                _bg_ai_content = ""
                for _m in reversed(_bg_new_msgs):
                    if isinstance(_m, AIMessage):
                        _bg_ai_content = _m.content
                        break
                if _bg_ai_content:
                    st.session_state.messages.append(AIMessage(content=_bg_ai_content))
                    if _bg_result.get("phase") == "checklist" and _bg_result.get("checklist"):
                        st.session_state.cb_checklist = _bg_result.get("checklist", [])
                        st.session_state.cb_checklist_answers = {}
                        st.session_state.cb_checklist_submitted = False
                        st.session_state.cb_issue = _bg_result.get("selected_issue", "")
                        st.session_state.cb_situation = _bg_result.get("situation", "")
                        st.session_state.cb_articles_by_issue = dict(_bg_result.get("articles_by_issue") or {})
                        st.session_state.cb_round = 1
                        st.session_state.cb_all_qa = []
                        st.session_state.cb_checklist_rag_results = list(_bg_result.get("checklist_rag_results") or [])
                        st.session_state.pending_buttons = []
                    else:
                        st.session_state.pending_buttons = []
                        if _bg_result.get("phase") == "conclusion":
                            st.session_state.cb_checklist = []
                            st.session_state.cb_checklist_answers = {}
                            st.session_state.cb_checklist_submitted = False
                else:
                    st.session_state.messages.append(AIMessage(content="응답을 생성하지 못했습니다. 다른 표현으로 다시 말씀해 주세요."))
                    st.session_state.pending_buttons = []
            # 결과 반영 완료 → "돌아가기" 버튼에 알림 뱃지 표시용 플래그
            st.session_state._result_just_arrived = True
            # 사용자가 조문 보기 중이라면 browse_view 유지 (사용자가 직접 돌아가기 선택)
    else:
        # 처리 중이 아닐 때는 플래그 초기화 (돌아가기 버튼 클릭 후 자동 소거)
        if st.session_state.get("browse_view") is None:
            st.session_state._result_just_arrived = False
    # ──────────────────────────────────────────────────────────────────────


    # ---------- 조항 상세 페이지 (법률 둘러보기에서 조항 클릭 시) ----------
    if st.session_state.get("browse_view") == "article_detail":
        art_num = st.session_state.get("browse_article_number") or ""
        ch_title = st.session_state.get("browse_chapter_title") or ""
        law_name = st.session_state.get("browse_law_name") or ""
        if art_num:
            paragraphs = st.session_state.get("browse_article_paragraphs") or []
            display_title = st.session_state.get("browse_article_title") or ""
            st.subheader(f"📜 {art_num} {display_title}".strip())
            # 메타 정보를 한 줄로 표시
            meta_parts = []
            if law_name:
                meta_parts.append(f"**{law_name}**")
            if ch_title:
                meta_parts.append(f"*{ch_title}*")
            if meta_parts:
                st.caption(" · ".join(meta_parts))
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
                        st.markdown("---")
                    prev_type = p_type
                    display_text = _strip_paragraph_text(p_type, text)
                    if p_type == "본문":
                        st.markdown(
                            f'<div style="background:#f8f9fa; border-left:3px solid #1f77b4; '
                            f'padding:0.6em 1em; border-radius:4px; margin-bottom:0.8em;">'
                            f'{display_text}</div>',
                            unsafe_allow_html=True
                        )
                    elif p_type == "항":
                        hang_num_map = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
                                        "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10"}
                        hang_num = hang_num_map.get(num, num) if num else ""
                        hlabel = f"제{hang_num}항" if hang_num else "항"
                        st.markdown(
                            f'<div style="margin-top:0.6em;">'
                            f'<span style="font-weight:600; color:#1f77b4; font-size:0.9em;">[{hlabel}]</span> '
                            f'{display_text}</div>',
                            unsafe_allow_html=True
                        )
                    elif p_type == "호":
                        label = f"{num.rstrip('.')}호" if num else "호"
                        st.markdown(
                            f'<div style="margin-left:2em; margin-top:0.4em; color:#444;">'
                            f'<span style="color:#888; font-size:0.85em;">{label}</span> {display_text}</div>',
                            unsafe_allow_html=True
                        )
                    elif p_type == "목":
                        label = f"{num}목" if num else "목"
                        st.markdown(
                            f'<div style="margin-left:4em; margin-top:0.3em; font-size:0.93em; color:#555;">'
                            f'<span style="color:#aaa; font-size:0.85em;">{label}</span> {display_text}</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(display_text)
            else:
                col = _cached_vector_store()
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
        
        # 처리 완료 여부 확인 후 버튼 레이블 변경 내용 반영
        _back_req = st.session_state.get("_processing_request_id")
        _back_msgs = st.session_state.get("messages") or []
        _back_last = _back_msgs[-1] if _back_msgs else None
        _back_done = (
            _back_req is None
            and isinstance(_back_last, AIMessage)
            and getattr(_back_last, "content", "") != CHECKLIST_PROCESSING_MSG
            and len(_back_msgs) > 1
        )
        _back_label = "← 챗봇으로 돌아가기 🔔" if _back_done and st.session_state.get("_result_just_arrived") else "← 챗봇으로 돌아가기"
        st.button(_back_label, type="primary", key="back_to_chat_from_article", on_click=_on_back_to_chat)
        return

    # 사이드바 렌더링 (fragment 외부)
    _render_sidebar()
    # @st.fragment으로 선언된 함수 — 채팅 영역만 부분 리런
    _render_chat_ui()


if __name__ == "__main__":
    main()
