"""
노동법 RAG 챗봇 - Streamlit UI
[4단계] 상황 입력 → 이슈 분류·선택 → 체크리스트 → 결론.
"""
import re
import streamlit as st
from rag import (
    build_vector_store,
    search,
    step1_issue_classification,
    step2_checklist,
    step3_conclusion,
    get_penalty_and_supplementary,
    filter_articles_by_issue_relevance,
)
from rag.store import search_by_article_numbers
from rag.law_json import (
    SCENARIO_QUICK,
    get_chapters,
    get_articles_by_chapter,
)
from config import (
    SOURCE_LAW,
    SOURCE_DECREE,
    SOURCE_RULE,
    ALL_LABOR_LAW_SOURCES,
    RAG_MAIN_TOP_K,
    RAG_AUX_TOP_K,
    RAG_DEF_TOP_K,
    RAG_FILTER_TOP_K,
)

# 체크리스트 반복: 확인할 게 없을 때까지 최대 N차까지 (정확도 향상)
CHECKLIST_MAX_ROUNDS = 3


def _source_to_tab_label(source: str) -> str:
    """메타데이터 source를 탭에 쓸 짧은 법률명으로 변환. (법률)/(시행령) 등 제거."""
    if not source:
        return "(출처 없음)"
    return source.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()


def _render_rag_results(results, title=None, show_summary_cards=True, filter_sources=None, max_text_per_article: int = 0):
    """RAG 검색 결과를 법률별 탭으로 나누어 표시. max_text_per_article이 0이면 조문 전문, 양수면 해당 글자 수까지."""
    if not results:
        return
    # 법률(source)별로 그룹화 (표시 순서 유지)
    by_source = {}
    for r in results:
        src = r.get("source", "") or "(출처 없음)"
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(r)
    with st.expander(title or "📜 이 단계에서 참조한 법령 조문 (RAG 검색 결과)", expanded=False):
        st.caption("아래 조문만을 바탕으로 답변이 생성되었습니다.")
        tab_labels = [_source_to_tab_label(s) for s in by_source.keys()]
        tabs = st.tabs(tab_labels)
        for tab, (source, items) in zip(tabs, by_source.items()):
            with tab:
                for i, r in enumerate(items, 1):
                    article = r.get("article", "")
                    text = (r.get("text") or "").strip()
                    chapter = r.get("chapter", "")
                    if max_text_per_article and len(text) > max_text_per_article:
                        text = text[:max_text_per_article] + " …"
                    header = f"**{i}. {article}**"
                    if chapter:
                        header += f" ({chapter})"
                    st.markdown(header)
                    st.write(text)
                    st.divider()


def show_rag_reference(collection, query: str, step_name: str, top_k: int = 8, filter_sources=None, exclude_sections=None, exclude_chapters=None, title=None, show_summary_cards: bool = True):
    """이 단계에서 참조한 법령 조문을 펼쳐보기로 표시 (쿼리로 검색). 실제 파이프라인과 동일한 결과를 보려면 파이프라인 반환값으로 _render_rag_results를 쓰세요."""
    results = search(collection, query, top_k=top_k, filter_sources=filter_sources, exclude_sections=exclude_sections, exclude_chapters=exclude_chapters)
    _render_rag_results(results, title=title, show_summary_cards=show_summary_cards, filter_sources=filter_sources)


def init_session():
    if "step" not in st.session_state:
        st.session_state.step = "input"
    if "collection" not in st.session_state:
        st.session_state.collection = None
    if "situation" not in st.session_state:
        st.session_state.situation = ""
    if "issues" not in st.session_state:
        st.session_state.issues = []
    if "selected_issue" not in st.session_state:
        st.session_state.selected_issue = ""
    if "qa_list" not in st.session_state:
        st.session_state.qa_list = []
    if "checklist" not in st.session_state:
        st.session_state.checklist = []
    if "selected_issues" not in st.session_state:
        st.session_state.selected_issues = []  # 복수 이슈 진행 시 [이슈1, 이슈2, ...]
    if "current_issue_index" not in st.session_state:
        st.session_state.current_issue_index = 0
    if "conclusions_list" not in st.session_state:
        st.session_state.conclusions_list = []  # [{"issue": str, "conclusion": str}, ...]
    if "qa_by_issue" not in st.session_state:
        st.session_state.qa_by_issue = []  # 이슈별 조항 구분 Q&A [ [qa1], [qa2], ... ]
    if "articles_by_issue" not in st.session_state:
        st.session_state.articles_by_issue = {}  # 이슈별 확정된 조문 {이슈명: [조문리스트]}
    if "checklist_answers" not in st.session_state:
        st.session_state.checklist_answers = []  # 체크리스트 질문에 대한 사용자 답변 [{question, answer}, ...]
    if "checklist_rag_results" not in st.session_state:
        st.session_state.checklist_rag_results = []  # step2에서 실제 사용한 RAG 검색 결과 (표시용)
    if "all_checklist_qa" not in st.session_state:
        st.session_state.all_checklist_qa = []  # 체크리스트 N차까지 누적 Q&A (다음 확인/결론용)
    if "checklist_round" not in st.session_state:
        st.session_state.checklist_round = 1  # 현재 체크리스트 차수 (1, 2, ...)
    if "browse_view" not in st.session_state:
        st.session_state.browse_view = None  # None | "article_detail"
    if "browse_article_number" not in st.session_state:
        st.session_state.browse_article_number = None
    if "browse_chapter_title" not in st.session_state:
        st.session_state.browse_chapter_title = ""
    if "browse_article_paragraphs" not in st.session_state:
        st.session_state.browse_article_paragraphs = []  # API에서 가져온 항 목록 [{num, text}, ...]
    if "browse_article_title" not in st.session_state:
        st.session_state.browse_article_title = ""


def _get_checklist_answers():
    """현재 체크리스트 입력값을 session_state에서 모아 반환."""
    checklist = st.session_state.get("checklist") or []
    return [
        {"question": item.get("question") or item.get("item") or "", "answer": st.session_state.get(f"checklist_{i}", "").strip()}
        for i, item in enumerate(checklist)
    ]


@st.cache_resource
def get_collection():
    return build_vector_store()[0]


def main():
    st.set_page_config(page_title="노동법 RAG 챗봇", layout="wide")
    init_session()

    # 벡터 스토어는 실패해도 UI(사이드바·추천 키워드)는 항상 표시되도록 먼저 그린 뒤 로드
    if st.session_state.collection is None:
        try:
            col = get_collection()
            st.session_state.collection = col
            st.session_state._load_error = None
        except Exception as e:
            st.session_state.collection = None
            st.session_state._load_error = str(e)

    # 사이드바: 설정 + 장별 브라우징 + 시나리오 바로가기
    with st.sidebar:
        st.header("설정")
        load_err = st.session_state.get("_load_error")
        if load_err:
            st.error("벡터 스토어 로드 실패. OPENAI_API_KEY·vector_store 확인 후 새로고침.")
            st.caption(load_err[:200] + ("…" if len(load_err) > 200 else ""))
        if st.button("벡터 스토어 재구축", use_container_width=True):
            with st.spinner("벡터 스토어 재구축 중..."):
                build_vector_store(force_rebuild=True)
            st.success("재구축 완료!")
            st.rerun()
        st.divider()
        st.subheader("📚 장(章)별 둘러보기")
        try:
            chapters = get_chapters()
        except Exception:
            chapters = []
        for ch in chapters[:14]:
            with st.expander(f"{ch['number']} {ch['title']}", expanded=False):
                articles = get_articles_by_chapter(ch["number"]) or []
                for i, a in enumerate(articles):
                    art_num = a.get("article_number", "")
                    title = a.get("title", "")
                    paras = a.get("paragraphs") or []
                    label = f"{art_num} {title}".strip() or art_num
                    if st.button(label, key=f"browse_{ch['number']}_{i}_{art_num}", use_container_width=True):
                        st.session_state.browse_view = "article_detail"
                        st.session_state.browse_article_number = art_num
                        st.session_state.browse_chapter_title = f"{ch.get('number','')} {ch.get('title','')}".strip()
                        st.session_state.browse_article_paragraphs = paras
                        st.session_state.browse_article_title = title
                        st.rerun()

    col = st.session_state.collection
    # ---------- 조항 상세 페이지 (장별 둘러보기에서 조항 클릭 시) ----------
    if st.session_state.get("browse_view") == "article_detail":
        art_num = st.session_state.get("browse_article_number") or ""
        ch_title = st.session_state.get("browse_chapter_title") or ""
        if art_num:
            paragraphs = st.session_state.get("browse_article_paragraphs") or []
            display_title = st.session_state.get("browse_article_title") or ""
            st.subheader(f"📜 {art_num} {display_title}".strip())
            if ch_title:
                st.caption(f"장: {ch_title}")
            st.divider()
            # 본문이 있는지 확인
            has_main_text = any(p.get("type") == "본문" for p in paragraphs)
            if paragraphs:
                prev_type = None
                for i, p in enumerate(paragraphs):
                    p_type = p.get("type", "")
                    num = p.get("num")
                    text = (p.get("text") or "").strip()
                    if not text:
                        continue
                    # 항이 끝나고 다음 항/본문이 오면 구분선 (호/목 다음에는 구분선 없음)
                    if prev_type == "항" and p_type != "호" and p_type != "목":
                        st.divider()
                    prev_type = p_type
                    # 항/호 본문에서 앞의 번호(②, 1. 등) 제거하여 표시
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
                    display_text = _strip_paragraph_text(p_type, text)
                    # 계층별 표시: 본문, 항(원문자), 호(숫자), 목(가나다)
                    if p_type == "본문":
                        st.markdown("### 본문")
                        st.markdown(display_text)
                    elif p_type == "항":
                        if num:
                            hang_num_map = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
                                            "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10"}
                            hang_num = hang_num_map.get(num, num)
                            label = f"### 제{hang_num}항"
                        else:
                            label = "### 항"
                        st.markdown(label)
                        st.markdown(display_text)
                    elif p_type == "호":
                        if num:
                            num_clean = num.rstrip(".")
                            label = f"-{num_clean}호"
                        else:
                            label = "-호"
                        st.markdown(f'<div style="margin-left: 2.5em; margin-top: 0.8em; margin-bottom: 0.3em; color: #666;">{label}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div style="margin-left: 2.5em; margin-bottom: 0.5em;">{display_text}</div>', unsafe_allow_html=True)
                    elif p_type == "목":
                        label = f"{num}목" if num else "목"
                        st.markdown(f'<div style="margin-left: 4.5em; margin-top: 0.3em; margin-bottom: 0.2em; font-size: 0.95em; color: #888;">{label}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div style="margin-left: 4.5em; font-size: 0.95em;">{display_text}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(display_text)
                # 마지막 항이 끝나면 구분선
                if prev_type == "항":
                    st.divider()
            elif col is not None:
                docs = search_by_article_numbers(col, [art_num], SOURCE_LAW)
                if docs:
                    r = docs[0]
                    title = r.get("article", "")
                    text = (r.get("text") or "").strip()
                    chapter = r.get("chapter", "")
                    source = r.get("source", "")
                    if chapter:
                        st.caption(f"장: {chapter}")
                    if source:
                        st.caption(f"출처: {source}")
                    st.markdown(text if text else "(본문 없음)")
                else:
                    st.warning(f"해당 조문({art_num}) 본문을 불러올 수 없습니다. 벡터 스토어에 포함되어 있는지 확인해 주세요.")
            else:
                st.warning("벡터 스토어를 불러올 수 없어 조문을 표시할 수 없습니다. 새로고침 후 다시 시도하세요.")
        else:
            st.info("조문을 선택해 주세요.")
        st.divider()
        if st.button("← 챗봇으로 돌아가기", type="primary", key="back_to_chat_from_article"):
            st.session_state.browse_view = None
            st.session_state.browse_article_number = None
            st.session_state.browse_chapter_title = ""
            st.session_state.browse_article_paragraphs = []
            st.session_state.browse_article_title = ""
            st.rerun()
        return

    st.title("노동법 RAG 챗봇")
    st.caption("근로기준법 등 노동법령 데이터 기반 상담")
    
    # ---------- 0. 상황 입력 ----------
    if st.session_state.step == "input":
        st.subheader("상황 입력")
        st.caption("시나리오 클릭 시 입력창에 자동 입력됩니다.")
        cols = st.columns(3)
        for i, s in enumerate(SCENARIO_QUICK):
            with cols[i % 3]:
                if st.button(s["label"], key=f"scenario_{s['label']}", use_container_width=True):
                    st.session_state.situation = s.get("situation", s.get("issue", ""))
                    st.rerun()
        st.divider()
        situation = st.text_area("상황을 입력해주세요", value=st.session_state.get("situation", ""), placeholder="예: 회사에서 돈을 못받았어요")
        if st.button("이슈 분류하기"):
            if not situation.strip():
                st.error("상황을 입력해주세요.")
            elif col is None:
                st.error("벡터 스토어를 불러올 수 없습니다. 사이드바 안내를 확인한 뒤 새로고침하세요.")
            else:
                st.session_state.situation = situation.strip()
                with st.spinner("이슈 분류 중... (보통 5~15초 걸립니다)"):
                    try:
                        issues, articles_by_issue, step1_source = step1_issue_classification(situation, collection=col)
                        if not issues:
                            st.error("제공된 법령 데이터에서 해당 상황에 맞는 이슈를 찾지 못했습니다. 다른 표현으로 다시 시도해 주세요.")
                        else:
                            st.session_state.issues = issues
                            st.session_state.articles_by_issue = articles_by_issue
                            st.session_state.step1_source = (step1_source or "llm").strip() if isinstance(step1_source, str) else "llm"
                            st.session_state.step = "issues"
                            st.rerun()
                    except Exception as e:
                        st.error(f"이슈 분류 중 오류가 발생했습니다: {str(e)}")
                        st.info("다시 시도하거나 다른 표현으로 입력해 주세요.")
        return
    
    # ---------- 1. 이슈 분류 결과 및 선택 ----------
    if st.session_state.step == "issues":
        st.write("**상황:** ", st.session_state.situation)
        issues = st.session_state.issues
        step1_source = st.session_state.get("step1_source") or "llm"
        st.success("감지된 이슈: " + ", ".join(issues))
        if step1_source == "keyword":
            st.caption("※ 입력하신 표현을 바탕으로 키워드 매칭으로 이슈를 찾았습니다.")
        else:
            st.caption("※ 검색된 법령 조문을 바탕으로 이슈를 분류했습니다.")
        # step1에서 반환한 이슈별 조문 사용 (중복 검색 제거)
        articles_by_issue = st.session_state.get("articles_by_issue") or {}
        # 이슈는 있는데 조문이 없으면(예: 이전 세션) 이슈별로 한 번만 검색해 채움
        for issue_item in issues:
            if issue_item not in articles_by_issue or not articles_by_issue[issue_item]:
                seen = set()
                issue_articles = []
                for q in [issue_item, st.session_state.situation]:
                    if not (q or str(q).strip()):
                        continue
                    res = search(
                        col, q, top_k=RAG_MAIN_TOP_K,
                        filter_sources=ALL_LABOR_LAW_SOURCES, exclude_sections=["벌칙", "부칙"],
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
        st.session_state.articles_by_issue = articles_by_issue

        # 전체 결과 표시용 (모든 이슈의 조문 합침)
        all_results = []
        seen_all = set()
        for issue_articles in articles_by_issue.values():
            for r in issue_articles:
                article_key = r.get("article", "")
                if article_key not in seen_all:
                    all_results.append(r)
                    seen_all.add(article_key)

        # 보완된 결과 표시 (법률별 탭)
        if all_results:
            _render_rag_results(all_results, title="📜 (법률 본칙) 이 단계에서 참조한 조문")
        st.caption("↑ 이슈 분류는 노동 관련 법률 조문을 기준으로 수행됩니다.")
        if len(issues) == 1:
            st.session_state.selected_issue = issues[0]
            st.session_state.selected_issues = [issues[0]]
            if st.button("다음: 체크리스트"):
                st.session_state.qa_list = []
                st.session_state.qa_by_issue = [[]]
                st.session_state.current_issue_index = 0
                st.session_state.checklist = None
                st.session_state.all_checklist_qa = []
                st.session_state.checklist_round = 1
                st.session_state.step = "checklist"
                st.rerun()
        else:
            if st.button("이슈 선택하기"):
                st.session_state.remaining_issues = issues
                st.session_state.step = "issue_select"
                st.rerun()
        if st.button("처음으로"):
            st.session_state.step = "input"
            st.rerun()
        return
    
    # ---------- 1-1. 이슈 선택 (복수 이슈) ----------
    if st.session_state.step == "issue_select":
        st.subheader("이슈 선택")
        remaining = st.session_state.get("remaining_issues", [])
        selected = st.multiselect("처리할 이슈를 선택하세요 (복수 선택 가능)", remaining, default=remaining)
        st.session_state.selected_issues = selected
        if st.button("체크리스트로"):
            if not selected:
                st.error("최소 1개 이슈를 선택해주세요.")
            else:
                st.session_state.current_issue_index = 0
                st.session_state.conclusions_list = []
                st.session_state.qa_by_issue = [[] for _ in selected]
                st.session_state.checklist = None
                st.session_state.all_checklist_qa = []
                st.session_state.checklist_round = 1
                st.session_state.step = "checklist"
                st.session_state.qa_list = []
                st.session_state.selected_issue = selected[0]
                st.rerun()
        if st.button("처음으로"):
            st.session_state.step = "input"
            st.rerun()
        return
    
    # ---------- 2. 체크리스트 ----------
    if st.session_state.step == "checklist":
        issue = st.session_state.selected_issue
        checklist = st.session_state.get("checklist")
        qa_list = list(st.session_state.qa_list)
        
        # 체크리스트가 없으면 생성
        if checklist is None:
            st.session_state.all_checklist_qa = st.session_state.get("all_checklist_qa") or []
            st.session_state.checklist_round = 1
            filter_preview = (issue + " " + "\n".join(f"Q: {x['question']} A: {x['answer']}" for x in qa_list))[:400]
            narrow_answers = [x.get("answer", "").strip() for x in qa_list if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
            remaining = list(st.session_state.get("articles_by_issue", {}).get(issue) or [])
            
            with st.spinner("체크리스트 생성 중... (보통 10~30초 걸립니다)"):
                try:
                    step2_res = step2_checklist(
                        issue, filter_preview, collection=col,
                        narrow_answers=narrow_answers or None,
                        qa_list=qa_list,
                        remaining_articles=remaining,
                        situation=st.session_state.get("situation") or "",
                    )
                    checklist = step2_res.get("checklist", []) or []
                    error_msg = step2_res.get("error")
                    if error_msg:
                        st.warning(f"체크리스트 생성에 문제가 있었습니다: {error_msg}")
                    st.session_state.checklist = checklist
                    st.session_state.checklist_rag_results = step2_res.get("rag_results", []) or []
                except Exception as e:
                    st.error(f"체크리스트 생성 중 오류가 발생했습니다: {str(e)}")
                    st.session_state.checklist = []
                    st.session_state.checklist_rag_results = []
            st.rerun()
            return

        # 체크리스트 단계에서 실제로 참조한 RAG 결과를 파이프라인 반환값으로 표시
        checklist_rag = st.session_state.get("checklist_rag_results") or []
        if checklist_rag:
            _render_rag_results(
                checklist_rag,
                title="📜 이 단계에서 참조한 법령 조문 (RAG 검색 결과)",
                show_summary_cards=True,
                filter_sources=ALL_LABOR_LAW_SOURCES,
            )
        else:
            filter_preview = (issue + " " + "\n".join(f"Q: {x['question']} A: {x['answer']}" for x in qa_list))[:400]
            narrow_answers = [x.get("answer", "").strip() for x in qa_list if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
            show_rag_reference(
                col,
                (issue + " " + " ".join(narrow_answers) + " " + filter_preview) if narrow_answers else filter_preview,
                "checklist",
                top_k=8,
                filter_sources=ALL_LABOR_LAW_SOURCES,
                exclude_sections=["벌칙", "부칙"],
                exclude_chapters=["제1장 총칙"],
            )
        round_n = st.session_state.get("checklist_round", 1)
        if round_n > 1:
            st.subheader(f"추가로 확인할 사항 ({round_n}차)")
            st.caption("아래는 이전 답변을 반영해 추가로 확인하는 질문입니다. 네/아니요/모르겠음 버튼을 눌러 주세요.")
        else:
            st.subheader(f"체크리스트: {issue}")
            st.caption("각 질문에 대해 네/아니요/모르겠음 버튼을 눌러 주세요.")
        if checklist:
            for i, item in enumerate(checklist):
                q = item.get("question") or item.get("item") or str(item)
                st.write(f"**{i+1}.** {q}")
                current = st.session_state.get(f"checklist_{i}", "").strip()
                c1, c2, c3, _ = st.columns([1, 1, 1, 2])
                with c1:
                    if st.button("네", key=f"checklist_btn_{i}_0", type="primary" if current == "네" else "secondary"):
                        st.session_state[f"checklist_{i}"] = "네"
                        st.rerun()
                with c2:
                    if st.button("아니요", key=f"checklist_btn_{i}_1", type="primary" if current == "아니요" else "secondary"):
                        st.session_state[f"checklist_{i}"] = "아니요"
                        st.rerun()
                with c3:
                    if st.button("모르겠음", key=f"checklist_btn_{i}_2", type="primary" if current == "모르겠음" else "secondary"):
                        st.session_state[f"checklist_{i}"] = "모르겠음"
                        st.rerun()
                if current:
                    st.caption(f"선택: **{current}**")
        else:
            st.warning("체크리스트가 생성되지 않았습니다. 결론으로 이동합니다.")
            if st.button("결론 생성하기", type="primary"):
                st.session_state.checklist_answers = []
                st.session_state.step = "conclusion"
                st.rerun()
                return

        # 누적 Q&A (이번 차수 포함) → 결론에서 사용
        current_answers = _get_checklist_answers()
        all_qa = list(st.session_state.get("all_checklist_qa") or []) + [x for x in current_answers if x.get("question") or x.get("answer")]
        
        # 모든 질문에 답변이 완료되었는지 확인
        all_answered = checklist and all(
            st.session_state.get(f"checklist_{i}", "").strip() in ("네", "아니요", "모르겠음")
            for i in range(len(checklist))
        )
        
        # AI가 자동으로 반복 여부 결정 (모든 질문에 답변이 완료되었을 때만)
        if all_answered and checklist:
            # 이전에 판단한 결과가 있으면 사용, 없으면 새로 판단
            should_continue = st.session_state.get("_checklist_should_continue")
            continuation_reason = st.session_state.get("_checklist_continuation_reason", "")
            
            if should_continue is None:
                # AI가 반복 여부 판단
                with st.spinner("AI가 추가 질문 필요 여부를 판단 중..."):
                    # 이번 차수 답변 누적
                    st.session_state.all_checklist_qa = all_qa
                    narrow_answers = [x.get("answer", "").strip() for x in all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
                    query = (issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else issue
                    new_results = search(
                        col, query, top_k=12,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                        exclude_sections=["벌칙", "부칙"],
                        exclude_chapters=["제1장 총칙"],
                    )
                    # 기존에 쓰던 조문 유지 + 새 검색 결과 병합
                    previous_articles = list(st.session_state.get("checklist_rag_results") or [])
                    if not previous_articles:
                        previous_articles = list(st.session_state.get("articles_by_issue", {}).get(issue) or [])
                    seen_art = {r.get("article", "") for r in previous_articles}
                    merged = list(previous_articles)
                    for r in new_results:
                        if r.get("article", "") and r.get("article", "") not in seen_art:
                            merged.append(r)
                            seen_art.add(r.get("article", ""))
                    filtered_text = (issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else issue
                    step2_res = step2_checklist(
                        issue, filtered_text, collection=col,
                        narrow_answers=narrow_answers or None,
                        qa_list=all_qa,
                        remaining_articles=merged,
                        situation=st.session_state.get("situation") or "",
                    )
                    should_continue = step2_res.get("should_continue", False)
                    continuation_reason = step2_res.get("continuation_reason", "")
                    st.session_state._checklist_should_continue = should_continue
                    st.session_state._checklist_continuation_reason = continuation_reason
                    
                    if should_continue:
                        new_checklist = step2_res.get("checklist", []) or []
                        if new_checklist:
                            st.info(f"💡 {continuation_reason or '추가 확인이 필요합니다.'}")
                            st.session_state.checklist = new_checklist
                            st.session_state.checklist_rag_results = step2_res.get("rag_results", []) or []
                            st.session_state.checklist_round = round_n + 1
                            st.session_state._checklist_should_continue = None  # 다음 라운드를 위해 초기화
                            for i in range(100):
                                st.session_state.pop(f"checklist_{i}", None)
                            st.rerun()
                            return
                        else:
                            # 체크리스트가 비어있으면 결론으로
                            st.info("추가 질문이 필요하지 않습니다. 결론을 생성합니다.")
                            st.session_state.checklist_answers = all_qa
                            st.session_state.step = "conclusion"
                            st.rerun()
                            return
                    else:
                        # 더 이상 질문이 필요 없음
                        st.success(f"✅ {continuation_reason or '충분한 정보를 수집했습니다. 결론을 생성합니다.'}")
                        st.session_state.checklist_answers = all_qa
                        st.session_state.step = "conclusion"
                        st.rerun()
                        return
            
            # 이미 판단한 결과가 있으면 그대로 진행
            if should_continue:
                new_checklist = st.session_state.get("checklist")
                if new_checklist:
                    st.info(f"💡 {continuation_reason or '추가 확인이 필요합니다.'}")
                    # 이미 다음 라운드로 진행됨
                    return
            else:
                st.success(f"✅ {continuation_reason or '충분한 정보를 수집했습니다. 결론을 생성합니다.'}")
                st.session_state.checklist_answers = all_qa
                st.session_state.step = "conclusion"
                st.rerun()
                return

        # 다음 확인으로: 답변으로 재검색 → 기존 조문 유지 + 새 조문 병합 후 추가 체크리스트 생성 (수동 버튼 - 선택사항)
        if round_n < CHECKLIST_MAX_ROUNDS and checklist and not all_answered:
            if st.button("다음 확인으로 (수동)", key="next_checklist_round"):
                # 이번 차수 답변 누적
                st.session_state.all_checklist_qa = all_qa
                narrow_answers = [x.get("answer", "").strip() for x in all_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
                query = (issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else issue
                with st.spinner("답변을 반영해 다시 검색한 뒤 추가 확인 질문을 만듭니다..."):
                    new_results = search(
                        col, query, top_k=12,
                        filter_sources=ALL_LABOR_LAW_SOURCES,
                        exclude_sections=["벌칙", "부칙"],
                        exclude_chapters=["제1장 총칙"],
                    )
                # 기존에 쓰던 조문 유지 + 새 검색 결과 병합 (1차 조문이 2차에서 사라지지 않도록)
                previous_articles = list(st.session_state.get("checklist_rag_results") or [])
                if not previous_articles:
                    previous_articles = list(st.session_state.get("articles_by_issue", {}).get(issue) or [])
                seen_art = {r.get("article", "") for r in previous_articles}
                merged = list(previous_articles)
                for r in new_results:
                    if r.get("article", "") and r.get("article", "") not in seen_art:
                        merged.append(r)
                        seen_art.add(r.get("article", ""))
                if not merged:
                    st.session_state.checklist_answers = all_qa
                    st.session_state.step = "conclusion"
                    st.rerun()
                    return
                filtered_text = (issue + " " + " ".join(narrow_answers))[:500] if narrow_answers else issue
                step2_res = step2_checklist(
                    issue, filtered_text, collection=col,
                    narrow_answers=narrow_answers or None,
                    qa_list=all_qa,
                    remaining_articles=merged,
                    situation=st.session_state.get("situation") or "",
                )
                new_checklist = step2_res.get("checklist", []) or []
                if not new_checklist:
                    st.session_state.checklist_answers = all_qa
                    st.session_state.step = "conclusion"
                    st.rerun()
                    return
                st.session_state.checklist = new_checklist
                st.session_state.checklist_rag_results = step2_res.get("rag_results", []) or []
                st.session_state.checklist_round = round_n + 1
                for i in range(100):
                    st.session_state.pop(f"checklist_{i}", None)
                st.rerun()
                return

        # 수동으로 결론으로 이동하는 버튼 (선택사항)
        if st.button("결론 생성하기 (수동)", key="manual_conclusion"):
            st.session_state.checklist_answers = all_qa
            st.session_state.step = "conclusion"
            st.rerun()
        selected_issues = st.session_state.get("selected_issues") or []
        current_idx = st.session_state.get("current_issue_index", 0)
        if len(selected_issues) > 1 and current_idx < len(selected_issues):
            is_last = (current_idx + 1) >= len(selected_issues)
            btn_label = "모든 결론 보기" if is_last else "다음 이슈로 (체크리스트·결론)"
            if st.button(btn_label):
                # 현재 이슈의 체크리스트 답변 반영 후 결론 저장
                checklist_ans = _get_checklist_answers()
                full_qa = qa_list + [x for x in checklist_ans if x.get("question") or x.get("answer")]
                narrow_ans = [x.get("answer", "").strip() for x in full_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
                
                with st.spinner("결론 생성 중..."):
                    res = step3_conclusion(issue, full_qa, collection=col, narrow_answers=narrow_ans if narrow_ans else None)
                    conclusion = res.get("conclusion", res) if isinstance(res, dict) else res
                    related_articles = res.get("related_articles", []) if isinstance(res, dict) else []
                    conclusions_list_ref = list(st.session_state.get("conclusions_list") or [])
                    st.session_state.conclusions_list = conclusions_list_ref + [{"issue": issue, "conclusion": conclusion, "related_articles": related_articles}]
                
                # 다음 이슈로 이동
                next_idx = current_idx + 1
                st.session_state.current_issue_index = next_idx
                if next_idx < len(selected_issues):
                    next_issue = selected_issues[next_idx]
                    qa_by_issue = st.session_state.get("qa_by_issue") or []
                    next_qa = list(qa_by_issue[next_idx]) if next_idx < len(qa_by_issue) else []
                    st.session_state.selected_issue = next_issue
                    st.session_state.qa_list = next_qa
                    st.session_state.checklist = None
                    st.rerun()
                    return
                else:
                    st.session_state.step = "all_conclusions"
                    st.rerun()
                    return
        if st.button("처음으로"):
            st.session_state.step = "input"
            st.rerun()
        return

    # ---------- 3. 결론 ----------
    if st.session_state.step == "conclusion":
        issue = st.session_state.selected_issue
        qa_list = list(st.session_state.qa_list)
        checklist_answers = list(st.session_state.get("checklist_answers") or [])
        # 타겟 질문 답변 + 체크리스트 답변을 합쳐서 결론에 반영
        full_qa_list = qa_list + [x for x in checklist_answers if x.get("question") or x.get("answer")]
        narrow_answers = [x.get("answer", "").strip() for x in full_qa_list if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]

        st.subheader(f"결론: {issue}")
        
        # 결론이 이미 생성되었는지 확인
        conclusion_result = st.session_state.get("_conclusion_result")
        
        if conclusion_result is None:
            # 결론 생성
            with st.spinner("결론 생성 중... (보통 15~30초 걸립니다)"):
                try:
                    res = step3_conclusion(issue, full_qa_list, collection=col, narrow_answers=narrow_answers if narrow_answers else None)
                    conclusion = res.get("conclusion", res) if isinstance(res, dict) else res
                    related_articles = res.get("related_articles", []) if isinstance(res, dict) else []
                    law_results = res.get("law_results", []) if isinstance(res, dict) else []
                    decree_rule_results = res.get("decree_rule_results", []) if isinstance(res, dict) else []
                    validation = res.get("validation", {}) if isinstance(res, dict) else {}
                    st.session_state._conclusion_result = {
                        "conclusion": conclusion,
                        "related_articles": related_articles,
                        "law_results": law_results,
                        "decree_rule_results": decree_rule_results,
                        "validation": validation,
                    }
                    # 검증 결과가 있으면 표시
                    if validation and not validation.get("has_citations", True):
                        st.warning("⚠️ 결론에 조문 인용이 없거나 검색 결과와 일치하지 않을 수 있습니다.")
                except Exception as e:
                    st.error(f"결론 생성 중 오류가 발생했습니다: {str(e)}")
                    st.session_state._conclusion_result = {
                        "conclusion": "결론 생성 중 오류가 발생했습니다. 다시 시도해 주세요.",
                        "related_articles": [],
                        "law_results": [],
                        "decree_rule_results": [],
                    }
            st.rerun()
            return
        
        conclusion = conclusion_result.get("conclusion", "")
        related_articles = conclusion_result.get("related_articles", [])
        law_results = conclusion_result.get("law_results", [])
        decree_rule_results = conclusion_result.get("decree_rule_results", [])

        # 결론 단계에서 실제로 참조한 RAG 결과를 파이프라인 반환값으로 표시
        if law_results:
            _render_rag_results(
                law_results,
                title="📜 (법률 본칙) 결론에 참조된 조문",
                show_summary_cards=True,
                filter_sources=ALL_LABOR_LAW_SOURCES,
            )
        if decree_rule_results:
            _render_rag_results(
                decree_rule_results,
                title="📜 (시행령·시행규칙) 결론에 참조된 조문",
                show_summary_cards=False,
                filter_sources=[SOURCE_DECREE, SOURCE_RULE],
            )
        st.session_state._last_conclusion = conclusion
        st.session_state._last_related_articles = related_articles
        st.write(conclusion)
        if related_articles:
            st.caption("📎 함께 확인해 보세요: " + ", ".join(related_articles))
        
        # 벌칙·부칙 조회
        penalty_supplementary = get_penalty_and_supplementary(col, conclusion, issue, full_qa_list)
        if penalty_supplementary:
            with st.expander("📜 해당 조항 관련 벌칙·부칙", expanded=False):
                st.caption("본칙에서 확정된 조항을 바탕으로 관련 벌칙·부칙을 검색한 결과입니다.")
                for i, r in enumerate(penalty_supplementary, 1):
                    source = r.get("source", "")
                    article = r.get("article", "")
                    text = (r.get("text") or "").strip()
                    section = r.get("section", "")
                    header = f"**[{i}] {source} · {article}**"
                    if section:
                        header = f"**[{i}] {source} · {article}** ({section})"
                    st.markdown(header)
                    st.write(text)
                    st.divider()

        selected_issues = st.session_state.get("selected_issues") or []
        current_idx = st.session_state.get("current_issue_index", 0)
        if len(selected_issues) > 1 and current_idx < len(selected_issues):
            is_last = (current_idx + 1) >= len(selected_issues)
            btn_label = "모든 결론 보기" if is_last else "다음 이슈로 (체크리스트·결론)"
            if st.button(btn_label):
                # 현재 이슈의 결론 저장 (이미 표시된 conclusion 사용)
                conc = st.session_state.get("_last_conclusion", conclusion)
                rel = st.session_state.get("_last_related_articles", related_articles)
                conclusions_list = list(st.session_state.get("conclusions_list") or [])
                conclusions_list.append({"issue": issue, "conclusion": conc, "related_articles": rel})
                st.session_state.conclusions_list = conclusions_list
                # 다음 이슈로
                st.session_state.current_issue_index = current_idx + 1
                if st.session_state.current_issue_index < len(selected_issues):
                    next_idx = st.session_state.current_issue_index
                    next_issue = selected_issues[next_idx]
                    qa_by_issue = st.session_state.get("qa_by_issue") or []
                    next_qa = list(qa_by_issue[next_idx]) if next_idx < len(qa_by_issue) else []
                    st.session_state.selected_issue = next_issue
                    st.session_state.qa_list = next_qa
                    filtered_text_next = "\n".join(f"Q: {x['question']}\nA: {x['answer']}" for x in next_qa) if next_qa else next_issue
                    narrow_next = [x.get("answer", "").strip() for x in next_qa if x.get("answer") and x.get("answer").strip() not in ("네", "아니요", "모르겠음", "(미입력)")]
                    remaining_next = list(st.session_state.get("articles_by_issue", {}).get(next_issue) or [])
                    with st.spinner("체크리스트 생성 중..."):
                        step2_res = step2_checklist(
                            next_issue, filtered_text_next, collection=col,
                            narrow_answers=narrow_next or None,
                            qa_list=next_qa,
                            remaining_articles=remaining_next,
                            situation=st.session_state.get("situation") or "",
                        )
                    st.session_state.checklist = step2_res.get("checklist", []) or []
                    st.session_state.checklist_rag_results = step2_res.get("rag_results", []) or []
                    st.session_state.all_checklist_qa = []
                    st.session_state.checklist_round = 1
                    for i in range(100):
                        st.session_state.pop(f"checklist_{i}", None)
                    st.session_state.step = "checklist"
                    st.rerun()
                else:
                    st.session_state.step = "all_conclusions"
                    st.rerun()
        elif len(selected_issues) > 1:
            if st.button("모든 결론 보기"):
                conclusions_list = list(st.session_state.get("conclusions_list") or [])
                conclusions_list.append({"issue": issue, "conclusion": conclusion, "related_articles": related_articles})
                st.session_state.conclusions_list = conclusions_list
                st.session_state.step = "all_conclusions"
                st.rerun()
        if st.button("처음으로"):
            st.session_state.step = "input"
            st.rerun()
        return

    # ---------- 5. 모든 결론 모아보기 (복수 이슈) ----------
    if st.session_state.step == "all_conclusions":
        st.subheader("이슈별 결론 모아보기")
        conclusions_list = st.session_state.get("conclusions_list") or []
        for i, item in enumerate(conclusions_list, 1):
            st.markdown(f"### {i}. {item.get('issue', '')}")
            st.write(item.get('conclusion', ''))
            rel = item.get("related_articles", [])
            if rel:
                st.caption("📎 함께 확인해 보세요: " + ", ".join(rel))
            st.divider()
        if st.button("처음으로"):
            st.session_state.step = "input"
            st.rerun()
        return


if __name__ == "__main__":
    main()
