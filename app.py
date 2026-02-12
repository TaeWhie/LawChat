"""
노동법 RAG 챗봇 - Streamlit UI
1. 상황 입력 → 이슈 분류(멀티) → 조항 구분 질문 → 체크리스트 → 결론
"""
import streamlit as st
from rag import (
    build_vector_store,
    step1_issue_classification,
    step2_provision_narrow,
    step3_checklist,
    step4_conclusion,
)


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
        st.session_state.selected_issue = None
    if "narrow" not in st.session_state:
        st.session_state.narrow = {}
    if "qa_list" not in st.session_state:
        st.session_state.qa_list = []
    if "checklist" not in st.session_state:
        st.session_state.checklist = []
    if "conclusion" not in st.session_state:
        st.session_state.conclusion = ""
    if "conclusion_issue" not in st.session_state:
        st.session_state.conclusion_issue = None


@st.cache_resource
def get_collection(force_rebuild: bool = False):
    return build_vector_store(force_rebuild=force_rebuild)


def main():
    st.set_page_config(page_title="노동법 RAG 챗봇", page_icon="⚖️", layout="centered")
    init_session()

    st.title("⚖️ 노동법 RAG 챗봇")
    st.caption("근로기준법 등 RAG 기반 · 모든 답변은 법령 데이터에만 근거합니다.")

    # 벡터 스토어 (캐시)
    if st.session_state.collection is None:
        with st.spinner("벡터 스토어 준비 중..."):
            st.session_state.collection = get_collection()
    col = st.session_state.collection

    # ---------- 0. 상황 입력 ----------
    if st.session_state.step == "input":
        st.subheader("상황 입력")
        situation = st.text_area(
            "겪고 계신 상황을 입력해 주세요.",
            placeholder="예: 회사에서 30일 통보 없이 해고당했어요.",
            height=120,
        )
        if st.button("이슈 분류하기", type="primary"):
            if not (situation and situation.strip()):
                st.warning("상황을 입력해 주세요.")
            else:
                st.session_state.situation = situation.strip()
                with st.spinner("상황에 따른 이슈 분류 중..."):
                    issues = step1_issue_classification(
                        st.session_state.situation,
                        collection=col,
                    )
                st.session_state.issues = issues or []
                if not st.session_state.issues:
                    st.info("제공된 법령 데이터에서 해당 상황에 맞는 이슈를 찾지 못했습니다.")
                else:
                    st.session_state.step = "issues"
                    st.rerun()
        return

    # ---------- 1. 이슈 선택 ----------
    if st.session_state.step == "issues":
        st.subheader("감지된 이슈")
        st.write("**상황:** ", st.session_state.situation)
        issues = st.session_state.issues
        st.success("감지된 이슈: " + ", ".join(issues))

        selected = st.radio(
            "진행할 이슈를 선택하세요.",
            options=issues,
            index=0,
        )
        st.session_state.selected_issue = selected

        if st.button("다음: 조항 구분 질문"):
            st.session_state.step = "narrow_qa"
            st.session_state.qa_list = []
            st.rerun()
        if st.button("처음으로"):
            st.session_state.step = "input"
            st.rerun()
        return

    # ---------- 2. 조항 구분 질문 ----------
    if st.session_state.step == "narrow_qa":
        issue = st.session_state.selected_issue
        st.subheader(f"조항 구분: {issue}")

        if not st.session_state.narrow or st.session_state.narrow.get("_issue") != issue:
            with st.spinner("관련 조항과 구분 질문 생성 중..."):
                narrow = step2_provision_narrow(issue, collection=col)
                st.session_state.narrow = {"_issue": issue, **narrow}

        narrow = st.session_state.narrow
        categories = narrow.get("categories", [])
        questions = narrow.get("questions", [])
        if categories:
            st.markdown("**관련 조항 카테고리:** " + " · ".join(categories))

        with st.form("narrow_form"):
            for i, q in enumerate(questions):
                st.text_input(f"Q{i+1}. {q}", key=f"narrow_q{i}")
            submitted = st.form_submit_button("체크리스트 생성")
        if submitted:
            qa_list = []
            for i, q in enumerate(questions):
                a = st.session_state.get(f"narrow_q{i}", "") or "(미입력)"
                qa_list.append({"question": q, "answer": a})
            st.session_state.qa_list = qa_list
            filtered_text = "\n".join(f"Q: {x['question']}\nA: {x['answer']}" for x in qa_list)
            with st.spinner("체크리스트 생성 중..."):
                checklist = step3_checklist(issue, filtered_text, collection=col)
            st.session_state.checklist = checklist or []
            st.session_state.step = "checklist"
            st.rerun()
        if st.button("이슈 선택으로 돌아가기"):
            st.session_state.step = "issues"
            st.session_state.narrow = {}
            st.rerun()
        return

    # ---------- 3. 체크리스트 ----------
    if st.session_state.step == "checklist":
        issue = st.session_state.selected_issue
        st.subheader(f"요건 검사: {issue}")
        checklist = st.session_state.checklist
        qa_list = list(st.session_state.qa_list)

        if not checklist:
            st.info("체크리스트가 생성되지 않았습니다. 결론으로 이동합니다.")
            if st.button("결론 생성"):
                st.session_state.step = "conclusion"
                st.session_state.qa_list = qa_list
                st.rerun()
        else:
            with st.form("checklist_form"):
                for i, item in enumerate(checklist):
                    q = item.get("question") or item.get("item") or str(item)
                    st.text_input(f"**{i+1}.** {q}", key=f"check_{i}")
                submitted = st.form_submit_button("결론 생성")
            if submitted:
                for i, item in enumerate(checklist):
                    q = item.get("question") or item.get("item") or str(item)
                    a = st.session_state.get(f"check_{i}", "") or "(미입력)"
                    qa_list.append({"question": q, "answer": a})
                st.session_state.qa_list = qa_list
                st.session_state.step = "conclusion"
                st.rerun()

        if st.button("조항 구분으로 돌아가기"):
            st.session_state.step = "narrow_qa"
            st.session_state.checklist = []
            st.rerun()
        return

    # ---------- 4. 결론 ----------
    if st.session_state.step == "conclusion":
        issue = st.session_state.selected_issue
        st.subheader("결론")

        if not st.session_state.conclusion or st.session_state.conclusion_issue != issue:
            with st.spinner("결론 생성 중..."):
                conclusion = step4_conclusion(
                    issue,
                    st.session_state.qa_list,
                    collection=col,
                )
                st.session_state.conclusion = conclusion
                st.session_state.conclusion_issue = issue

        st.markdown("---")
        st.markdown(st.session_state.conclusion)
        st.markdown("---")

        if st.button("새 상담 시작"):
            for key in list(st.session_state.keys()):
                if key != "collection":
                    del st.session_state[key]
            init_session()
            st.session_state.collection = col
            st.rerun()


if __name__ == "__main__":
    main()
