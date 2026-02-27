"""
LawChat 프롬프트 실험 도구 (Streamlit) — 실제 서버 API 호출
의도 분류 / 이슈 분류 / 체크리스트 / 결론 / 지식·계산·예외·문서 실험.

실행: streamlit run app_playground.py
(서버가 localhost:8000 이면 먼저 uvicorn main_api:app --reload 로 기동)

환경변수·시크릿 없음. API 서버 주소는 아래 상수만 사용.
"""
import json
import time
import uuid
import streamlit as st
import requests

try:
    from rag.labor_keywords import PRIMARY_ISSUES
except ImportError:
    PRIMARY_ISSUES = (
        "임금", "퇴직금", "해고/징계", "근로계약", "휴일/휴가", "근로시간",
        "직장 내 괴롭힘", "근로자 보호", "산재", "산업안전", "노조",
        "최저임금", "남녀고용평등", "육아휴직", "고용보험",
    )

# API 서버 URL (원하는 주소로 수정)
DEFAULT_BASE_URL = "https://law-chat-api.onrender.com"
TIMEOUT = 90

# 모드별 프롬프트 키
MODE_PROMPT_KEYS = {
    "의도 분류": [],  # 규칙 기반
    "이슈 분류": ["system_issue_classification", "user_issue_classification"],
    "체크리스트": [
        "system_checklist", "user_checklist",
        "system_checklist_continuation", "user_checklist_continuation",
    ],
    "결론": ["system_conclusion", "user_conclusion"],
    "지식": ["system_knowledge_qa", "user_knowledge_qa"],
    "계산": ["system_calculation_qa", "user_calculation_qa"],
    "예외": ["system_exception_qa", "user_exception_qa"],
    "문서": [],
}


def get_base_url():
    return DEFAULT_BASE_URL


def get_api_key():
    return st.session_state.get("playground_api_key", "").strip()


def api_get(path: str):
    url = f"{get_base_url()}{path}"
    try:
        r = requests.get(url, timeout=15)
        return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except requests.exceptions.RequestException as e:
        return -1, {"error": str(e)}


def api_post(path: str, body: dict):
    url = f"{get_base_url()}{path}"
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return r.status_code, data
    except requests.exceptions.RequestException as e:
        return -1, {"error": str(e), "detail": str(e)}


def render_sidebar():
    st.sidebar.header("설정")
    st.session_state["playground_api_key"] = st.sidebar.text_input(
        "OpenAI API Key",
        value=st.session_state.get("playground_api_key", ""),
        type="password",
        help="LLM API 호출에 필수",
    )
    if st.sidebar.button("연결 확인 (Health)"):
        code, data = api_get("/api/v1/health")
        if code == 200:
            st.sidebar.success("연결됨")
        else:
            st.sidebar.error(f"실패: {code} {data}")


def main():
    st.set_page_config(page_title="LawChat 프롬프트 실험", layout="wide")
    st.title("LawChat 프롬프트 실험 도구")
    render_sidebar()

    api_key = get_api_key()
    if not api_key:
        st.info("👈 **사이드바**에서 **OpenAI API Key**를 입력한 뒤 사용하세요. (입력하지 않으면 실행만 불가합니다.)")
    else:
        st.caption("API 서버: " + get_base_url())

    mode = st.selectbox(
        "실험 모드",
        ["의도 분류", "이슈 분류", "체크리스트", "결론", "지식", "계산", "예외", "문서"],
        key="playground_mode",
    )

    # 프롬프트 기본값 불러오기
    prompt_keys = MODE_PROMPT_KEYS.get(mode, [])
    if prompt_keys and st.checkbox("프롬프트 오버라이드 사용", value=False, key="use_overrides"):
        if st.button("기본 프롬프트 불러오기 (GET /api/v1/prompts)"):
            code, data = api_get("/api/v1/prompts")
            if code == 200 and "prompts" in data:
                prompts = data["prompts"]
                for k in prompt_keys:
                    if k not in st.session_state.get("playground_prompts", {}):
                        st.session_state.setdefault("playground_prompts", {})[k] = prompts.get(k, "")
                st.session_state["playground_prompts_loaded"] = True
                st.rerun()
        if st.session_state.get("playground_prompts_loaded"):
            overrides = {}
            for k in prompt_keys:
                overrides[k] = st.text_area(k, value=st.session_state.get("playground_prompts", {}).get(k, ""), height=120, key=f"prompt_{k}")
            st.session_state["playground_overrides"] = {k: v for k, v in overrides.items() if v.strip()}
    else:
        st.session_state["playground_overrides"] = {}

    overrides = st.session_state.get("playground_overrides") or {}

    # ----- 의도 분류 -----
    if mode == "의도 분류":
        st.subheader("의도 분류 (질문 유형)")
        text = st.text_area("메시지 (text)", value="퇴직금이 뭐예요?", height=80, key="route_text")
        if st.button("실행 (POST /api/v1/chat/route)"):
            if not api_key:
                st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
            else:
                body = {"text": text, "openai_api_key": api_key}
                with st.spinner("호출 중..."):
                    code, data = api_post("/api/v1/chat/route", body)
                if code == 200:
                    qtype = data.get("question_type", "")
                    st.success(f"**question_type:** `{qtype}`")
                    st.json(data)
                else:
                    st.error(f"에러 {code}: {data}")

    # ----- 이슈 분류 -----
    elif mode == "이슈 분류":
        st.subheader("이슈 분류")
        situation = st.text_area("situation", value="월급을 두 달째 못 받았어요.", height=100, key="classify_situation")
        top_k = st.number_input("top_k", min_value=1, max_value=50, value=22, key="classify_topk")
        if st.button("실행 (POST /api/v1/chat/classify)"):
            if not api_key:
                st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
            else:
                body = {"situation": situation, "top_k": top_k, "openai_api_key": api_key}
                if overrides:
                    body["prompt_overrides"] = overrides
                with st.spinner("호출 중..."):
                    code, data = api_post("/api/v1/chat/classify", body)
                if code == 200:
                    issues = data.get("issues", [])
                    st.success(f"**issues:** {issues}")
                    with st.expander("articles_by_issue"):
                        st.json(data.get("articles_by_issue", {}))
                    st.json(data)
                else:
                    st.error(f"에러 {code}: {data}")

    # ----- 체크리스트 -----
    elif mode == "체크리스트":
        st.subheader("체크리스트")
        st.caption("situation에 따라 이슈가 정해지므로, 먼저 **이슈 분류**를 실행한 뒤 나온 이슈로 체크리스트를 생성합니다. 응답에는 **should_continue**(추가 질문 라운드 필요 여부), **continuation_reason**(판단 이유)가 포함되며, **첫 라운드에서도** 반복 여부가 판단됩니다.")
        situation = st.text_area("situation", value="월급을 두 달째 못 받았어요.", height=80, key="cl_situation")
        # 1단계: 이슈 분류
        if st.button("1단계: 이슈 분류 실행 (situation → issues)"):
            if not api_key:
                st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
            else:
                body = {"situation": situation, "top_k": 22, "openai_api_key": api_key}
                if overrides:
                    body["prompt_overrides"] = overrides
                with st.spinner("classify 호출 중..."):
                    code, data = api_post("/api/v1/chat/classify", body)
                if code == 200:
                    issues = data.get("issues", [])
                    if issues:
                        st.session_state["playground_cl_issues"] = issues
                        st.session_state["playground_cl_articles"] = data.get("articles_by_issue", {})
                        st.success(f"분류된 이슈: {issues}")
                    else:
                        st.warning("분류된 이슈가 없습니다.")
                else:
                    st.error(f"에러 {code}: {data}")

        issues_from_classify = st.session_state.get("playground_cl_issues", [])
        if issues_from_classify:
            issue = st.radio(
                "체크리스트에 사용할 이슈 (위에서 분류된 결과 중 선택)",
                options=issues_from_classify,
                key="cl_issue_radio",
            )
        else:
            issue = None
            st.info("위에서 **1단계: 이슈 분류 실행**을 먼저 눌러 주세요.")

        # 이전 라운드까지의 Q&A 누적 (첫 실행 후 답변 입력 → 2라운드 실행 시 사용)
        accumulated_qa = st.session_state.get("playground_cl_accumulated_qa", [])
        last_questions = st.session_state.get("playground_cl_last_questions", [])
        last_response = st.session_state.get("playground_cl_last_response")
        last_round = st.session_state.get("playground_cl_last_round", 0)

        # 고급: all_qa·round 직접 입력 (첫 라운드 전이거나 수동 제어할 때)
        with st.expander("고급: all_qa · round 직접 입력 (비우면 첫 라운드)"):
            all_qa_text = st.text_area("all_qa (JSON 배열)", value=json.dumps(accumulated_qa, ensure_ascii=False, indent=2) if accumulated_qa else "[]", height=100, key="cl_all_qa")
            round_num = st.number_input("round", min_value=1, value=last_round + 1 if last_round else 1, key="cl_round", help="API에 전달할 라운드 번호. 일반 플로우에서는 자동으로 1→2→3... 적용됩니다.")
        try:
            all_qa = json.loads(all_qa_text) if all_qa_text.strip() else []
        except json.JSONDecodeError:
            all_qa = accumulated_qa if accumulated_qa else []
            st.warning("all_qa는 JSON 배열이어야 합니다. 예: [{\"question\":\"...\", \"answer\":\"네\"}]")
        round_num = st.session_state.get("cl_round", last_round + 1 if last_round else 1)

        if st.button("2단계: 체크리스트 실행 (POST /api/v1/chat/checklist)"):
            if not api_key:
                st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
            elif not issue:
                st.warning("먼저 **1단계: 이슈 분류 실행**으로 이슈를 받은 뒤 실행해 주세요.")
            else:
                body = {
                    "issue": issue,
                    "situation": situation,
                    "all_qa": all_qa,
                    "round": round_num,
                    "previous_rag_results": [],
                    "openai_api_key": api_key,
                }
                if overrides:
                    body["prompt_overrides"] = overrides
                with st.spinner("호출 중..."):
                    code, data = api_post("/api/v1/chat/checklist", body)
                if code == 200:
                    checklist = data.get("checklist", [])
                    # 세션에 저장 → 아래에서 답변 입력란 + 2라운드 실행 버튼 표시
                    q_list = []
                    for item in checklist:
                        q = item.get("question") or item.get("item") or str(item)
                        q_list.append(q)
                    st.session_state["playground_cl_last_response"] = data
                    st.session_state["playground_cl_last_questions"] = q_list
                    st.session_state["playground_cl_accumulated_qa"] = all_qa
                    st.session_state["playground_cl_last_round"] = int(round_num)
                    st.session_state["playground_cl_issue"] = issue
                    st.session_state["playground_cl_situation"] = situation
                    history = st.session_state.get("playground_cl_history", [])
                    history_entry = {
                        "issue": issue,
                        "situation": situation,
                        "round": int(round_num),
                        "all_qa": all_qa,
                        "response": data,
                        "saved_at": time.time(),
                    }
                    st.session_state["playground_cl_history"] = history + [history_entry]
                    st.rerun()
                else:
                    st.error(f"에러 {code}: {data}")

        # 이전 체크리스트 실행 결과가 있으면: 반복 판단 표시 + 답변 입력란 + 2라운드 실행 버튼
        if last_response and last_questions is not None:
            st.divider()
            st.subheader("반복 판단 및 답변 입력")
            should_continue = last_response.get("should_continue")
            reason = last_response.get("continuation_reason", last_response.get("reason", ""))
            if should_continue is True:
                st.info(f"**반복 여부:** 추가 질문 필요 (`should_continue: true`)  \n**판단 이유:** {reason}" if reason else "**반복 여부:** 추가 질문 필요 (`should_continue: true`)")
            elif should_continue is False:
                st.success(f"**반복 여부:** 결론 단계로 진행 가능 (`should_continue: false`)  \n**판단 이유:** {reason}" if reason else "**반복 여부:** 결론 단계로 진행 가능 (`should_continue: false`)")
            elif should_continue is None:
                st.caption("**반복 여부:** 판단 없음 (`should_continue: null`)")

            # 체크리스트 질문에 사용된 참고 조문 표시
            provisions_summary = last_response.get("related_provisions_summary", [])
            rag_results = last_response.get("rag_results", [])
            if provisions_summary:
                with st.expander("📜 체크리스트 참고 조문 (이 질문들을 만들 때 참고한 조항)", expanded=True):
                    for i, prov in enumerate(provisions_summary, 1):
                        st.markdown(f"{i}. {prov}")
                    st.caption("결론 단계에서도 동일/유사 조문을 바탕으로 답변합니다.")
            elif rag_results:
                with st.expander("📜 체크리스트 참고 조문 (rag_results)", expanded=True):
                    for i, r in enumerate(rag_results[:15], 1):
                        src = (r.get("source") or "").replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
                        art = r.get("article") or ""
                        text = (r.get("text") or r.get("content") or "")[:200]
                        st.markdown(f"**{i}. {src} {art}**\n{text}...")
                    st.caption("결론 단계에서도 동일/유사 조문을 바탕으로 답변합니다.")

            st.caption(f"아래 질문마다 **예 / 아니오 / 모르겠음** 중 하나를 선택한 뒤 **「답변 반영 후 다음 라운드 실행」**을 누르세요. (현재까지 누적 Q&A: {len(accumulated_qa)}개)")
            ANSWER_OPTIONS = ["예", "아니오", "모르겠음"]
            for i, q in enumerate(last_questions):
                st.radio(
                    f"**Q{i+1}.** {q}",
                    options=ANSWER_OPTIONS,
                    index=0,
                    key=f"cl_answer_{i}",
                    horizontal=True,
                )

            next_round = last_round + 1
            if st.button("답변 반영 후 다음 라운드 실행 (2라운드 체크리스트)"):
                if not api_key:
                    st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
                else:
                    answers = [st.session_state.get(f"cl_answer_{i}", "").strip() for i in range(len(last_questions))]
                    new_qa = list(accumulated_qa) + [{"question": q, "answer": a or "(답변 없음)"} for q, a in zip(last_questions, answers)]
                    body = {
                        "issue": st.session_state.get("playground_cl_issue", issue),
                        "situation": st.session_state.get("playground_cl_situation", situation),
                        "all_qa": new_qa,
                        "round": next_round,
                        "previous_rag_results": [],
                        "openai_api_key": api_key,
                    }
                    if overrides:
                        body["prompt_overrides"] = overrides
                    with st.spinner("다음 라운드 체크리스트 호출 중..."):
                        code, data = api_post("/api/v1/chat/checklist", body)
                    if code == 200:
                        checklist2 = data.get("checklist", [])
                        q_list2 = [item.get("question") or item.get("item") or str(item) for item in checklist2]
                        st.session_state["playground_cl_last_response"] = data
                        st.session_state["playground_cl_last_questions"] = q_list2
                        st.session_state["playground_cl_accumulated_qa"] = new_qa
                        st.session_state["playground_cl_last_round"] = next_round
                        issue_used = st.session_state.get("playground_cl_issue", issue)
                        situation_used = st.session_state.get("playground_cl_situation", situation)
                        history = st.session_state.get("playground_cl_history", [])
                        history_entry = {
                            "issue": issue_used,
                            "situation": situation_used,
                            "round": next_round,
                            "all_qa": new_qa,
                            "response": data,
                            "saved_at": time.time(),
                        }
                        st.session_state["playground_cl_history"] = history + [history_entry]
                        # 이전 답변 위젯 키 초기화해 새 질문에 맞춤 (선택적)
                        for j in range(len(last_questions)):
                            if f"cl_answer_{j}" in st.session_state:
                                del st.session_state[f"cl_answer_{j}"]
                        st.rerun()
                    else:
                        st.error(f"에러 {code}: {data}")

            if accumulated_qa:
                with st.expander("현재까지 누적 Q&A"):
                    for i, qa in enumerate(accumulated_qa):
                        q = qa.get("question", qa.get("q", ""))
                        a = qa.get("answer", qa.get("a", ""))
                        st.markdown(f"**Q{i+1}.** {q}  \n→ {a}")
                    st.caption("👇 결론 탭 **all_qa**에 그대로 붙여넣기:")
                    st.text_area(
                        "결론 탭에 붙여넣기용 JSON",
                        value=json.dumps(accumulated_qa, ensure_ascii=False, indent=2),
                        height=120,
                        key="cl_accumulated_qa_json",
                        help="전체 선택(Ctrl+A) 후 복사한 뒤, 결론 탭의 all_qa 입력란에 붙여넣으세요.",
                    )
            with st.expander("마지막 체크리스트 전체 응답"):
                st.json(last_response)

        history = st.session_state.get("playground_cl_history", [])
        if history:
            st.divider()
            st.subheader("저장된 체크리스트 기록")
            for idx, item in enumerate(reversed(history), 1):
                ts = item.get("saved_at")
                ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else ""
                header = f"[{idx}] {item.get('issue', '(이슈 없음)')} / round {item.get('round')} / {ts_str}"
                with st.expander(header):
                    st.markdown(f"**situation**: {item.get('situation', '')}")
                    st.json(item.get("response", {}))
            st.download_button(
                "전체 체크리스트 기록 JSON 다운로드",
                data=json.dumps(history, ensure_ascii=False, indent=2),
                file_name="checklist_history.json",
                mime="application/json",
            )

        # ----- 자동 이슈별 체크리스트 시뮬레이션 -----
        st.divider()
        with st.expander("자동 이슈별 체크리스트 시뮬레이션 (테스트용)", expanded=False):
            st.caption("situation을 한 번 입력하면, 이슈 분류 → 각 이슈별 체크리스트를 여러 라운드까지 자동으로 돌려서 결과를 모아줍니다. Q&A 답변은 선택한 기본값으로 자동 채우며, 실제 사건 상담용이 아닌 **프롬프트/체크리스트 구조 검증용**입니다.")
            auto_situation = st.text_area(
                "situation (자동 시뮬레이션용)",
                value=situation,
                height=80,
                key="auto_cl_situation",
            )
            col1, col2, col3 = st.columns(3)
            with col1:
                auto_top_k = st.number_input(
                    "이슈 분류 top_k",
                    min_value=1,
                    max_value=50,
                    value=10,
                    key="auto_cl_topk",
                )
            with col2:
                max_issues = st.number_input(
                    "최대 이슈 개수",
                    min_value=1,
                    max_value=50,
                    value=5,
                    key="auto_cl_max_issues",
                    help="이슈 분류 결과 중 상위 몇 개 이슈에 대해 체크리스트를 돌릴지 설정합니다.",
                )
            with col3:
                max_rounds = st.number_input(
                    "이슈별 최대 라운드 수",
                    min_value=1,
                    max_value=10,
                    value=3,
                    key="auto_cl_max_rounds",
                    help="각 이슈별로 체크리스트를 최대 몇 라운드까지 반복 호출할지 설정합니다.",
                )
            answer_default = st.selectbox(
                "자동 Q&A에서 사용할 기본 답변",
                options=["예", "아니오", "모르겠음"],
                index=2,
                key="auto_cl_default_answer",
                help="각 라운드에서 생성된 질문에 대해 이 값으로 자동 답변을 채워 다음 라운드를 호출합니다.",
            )

            if st.button("자동 이슈별 체크리스트 전체 실행", key="auto_cl_run"):
                if not api_key:
                    st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
                else:
                    with st.spinner("이슈 분류 및 이슈별 체크리스트 자동 실행 중..."):
                        # 1단계: situation으로 이슈 분류
                        classify_body = {
                            "situation": auto_situation,
                            "top_k": int(auto_top_k),
                            "openai_api_key": api_key,
                        }
                        if overrides:
                            classify_body["prompt_overrides"] = overrides
                        code_c, data_c = api_post("/api/v1/chat/classify", classify_body)
                        if code_c != 200:
                            st.error(f"이슈 분류 에러 {code_c}: {data_c}")
                        else:
                            issues_auto = data_c.get("issues", [])[: int(max_issues)]
                            if not issues_auto:
                                st.warning("이슈 분류 결과가 없습니다.")
                            else:
                                auto_results = []
                                for iss in issues_auto:
                                    all_qa_auto = []
                                    previous_rag = []
                                    for r in range(1, int(max_rounds) + 1):
                                        body_cl = {
                                            "issue": iss,
                                            "situation": auto_situation,
                                            "all_qa": all_qa_auto,
                                            "round": r,
                                            "previous_rag_results": previous_rag,
                                            "openai_api_key": api_key,
                                        }
                                        if overrides:
                                            body_cl["prompt_overrides"] = overrides
                                        code_cl, data_cl = api_post("/api/v1/chat/checklist", body_cl)
                                        if code_cl != 200:
                                            auto_results.append(
                                                {
                                                    "issue": iss,
                                                    "situation": auto_situation,
                                                    "round": r,
                                                    "all_qa": list(all_qa_auto),
                                                    "error": {"status_code": code_cl, "data": data_cl},
                                                }
                                            )
                                            break
                                        checklist_items = data_cl.get("checklist", [])
                                        questions = [
                                            (item.get("question") or item.get("item") or str(item))
                                            for item in checklist_items
                                        ]
                                        should_continue_auto = data_cl.get("should_continue")
                                        auto_results.append(
                                            {
                                                "issue": iss,
                                                "situation": auto_situation,
                                                "round": r,
                                                "all_qa": list(all_qa_auto),
                                                "questions": questions,
                                                "should_continue": should_continue_auto,
                                                "response": data_cl,
                                            }
                                        )
                                        # 다음 라운드를 위한 자동 Q&A 누적
                                        if not questions:
                                            break
                                        new_pairs = [
                                            {"question": q, "answer": answer_default} for q in questions
                                        ]
                                        all_qa_auto = all_qa_auto + new_pairs
                                        previous_rag = data_cl.get("rag_results") or []
                                        if should_continue_auto is not True:
                                            break
                                st.session_state["playground_auto_cl_results"] = auto_results

                    auto_results = st.session_state.get("playground_auto_cl_results", [])
                    if auto_results:
                        st.success(f"자동 실행 완료 (총 {len(auto_results)}개 라운드 결과). 아래에서 이슈·라운드별로 확인하거나 JSON으로 다운로드할 수 있습니다.")

            auto_results_view = st.session_state.get("playground_auto_cl_results", [])
            if auto_results_view:
                st.markdown("#### 자동 실행 결과 요약")
                # 이슈별로 그룹핑
                issue_map = {}
                for item in auto_results_view:
                    issue_key = item.get("issue", "(이슈 없음)")
                    issue_map.setdefault(issue_key, []).append(item)
                for iss, items in issue_map.items():
                    with st.expander(f"[자동] 이슈: {iss} (라운드 {len(items)}개)", expanded=False):
                        for it in items:
                            header = f"round {it.get('round')}"
                            should_c = it.get("should_continue")
                            sc_str = (
                                " (should_continue: true)"
                                if should_c is True
                                else " (should_continue: false)"
                                if should_c is False
                                else " (should_continue: null)"
                                if should_c is None
                                else ""
                            )
                            st.markdown(f"**{header}{sc_str}**")
                            if "error" in it:
                                st.error(it["error"])
                            else:
                                qs = it.get("questions") or []
                                if qs:
                                    for i, q in enumerate(qs, 1):
                                        st.markdown(f"- Q{i}. {q}")
                                with st.expander("원시 응답(JSON)", expanded=False):
                                    st.json(it.get("response", {}))
                st.download_button(
                    "자동 실행 결과 JSON 다운로드",
                    data=json.dumps(auto_results_view, ensure_ascii=False, indent=2),
                    file_name="auto_checklist_results.json",
                    mime="application/json",
                    key="auto_cl_download",
                )

    # ----- 결론 -----
    elif mode == "결론":
        st.subheader("결론")
        issue = st.selectbox(
            "issue (인식 가능한 이슈만 선택)",
            options=list(PRIMARY_ISSUES),
            key="conc_issue",
        )
        all_qa_text = st.text_area("all_qa (JSON 배열)", value='[{"question":"2개월 이상 체불되었나요?","answer":"네"}]', height=120, key="conc_all_qa")
        try:
            all_qa = json.loads(all_qa_text) if all_qa_text.strip() else []
        except json.JSONDecodeError:
            all_qa = []
            st.warning("all_qa는 JSON 배열이어야 합니다.")
        # 체크리스트 탭에서 실행한 결과의 rag_results가 있으면 결론 AI가 해당 조문을 함께 참고하도록 전달
        cl_rag = st.session_state.get("playground_cl_last_response", {}).get("rag_results") or []
        use_cl_rag = len(cl_rag) > 0
        if use_cl_rag:
            st.caption(f"✅ 체크리스트 참고 조문 {len(cl_rag)}개가 결론 API에 함께 전달됩니다 (같은 조문 기준으로 결론 생성).")
        if st.button("실행 (POST /api/v1/chat/conclusion)"):
            if not api_key:
                st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
            else:
                body = {"issue": issue, "all_qa": all_qa, "openai_api_key": api_key}
                if use_cl_rag:
                    body["checklist_rag_results"] = cl_rag
                if overrides:
                    body["prompt_overrides"] = overrides
                with st.spinner("호출 중..."):
                    code, data = api_post("/api/v1/chat/conclusion", body)
                if code == 200:
                    conclusion = data.get("conclusion", "")
                    st.success("**결론**")
                    st.markdown(conclusion)
                    if data.get("related_articles"):
                        st.caption("관련 조문: " + ", ".join(data.get("related_articles", [])))
                    with st.expander("전체 응답"):
                        st.json(data)
                else:
                    st.error(f"에러 {code}: {data}")

    # ----- 지식 / 계산 / 예외 / 문서 (invoke) -----
    elif mode in ("지식", "계산", "예외", "문서"):
        st.subheader(mode + " (invoke)")
        message = st.text_area(
            "message",
            value=(
                "퇴직금이 뭐예요?" if mode == "지식"
                else "2022년 1월 입사 2024년 2월 퇴사 월급 300만원이면 퇴직금은?" if mode == "계산"
                else "올해 최저임금은 얼마야?" if mode == "예외"
                else "퇴직금 받을 때 필요한 서류가 뭐가 있나요?"
            ),
            height=100,
            key="invoke_msg",
        )
        invoke_overrides = overrides
        if st.button(f"실행 (POST /api/v1/chat/invoke)"):
            if not api_key:
                st.warning("OpenAI API Key를 사이드바에 입력해 주세요.")
            else:
                thread_id = f"playground-{mode}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
                body = {
                    "message": message,
                    "thread_id": thread_id,
                    "openai_api_key": api_key,
                }
                if invoke_overrides:
                    body["prompt_overrides"] = invoke_overrides
                with st.spinner("호출 중..."):
                    code, data = api_post("/api/v1/chat/invoke", body)
                if code == 200:
                    messages = data.get("messages", [])
                    last_ai = None
                    for m in reversed(messages):
                        if isinstance(m, dict) and m.get("t") == "AIMessage" and m.get("c"):
                            last_ai = m.get("c", "")
                            break
                    if last_ai:
                        st.success("**응답**")
                        st.markdown(last_ai)
                    st.caption(f"phase: {data.get('phase')} | thread_id: {thread_id}")
                    with st.expander("전체 응답"):
                        st.json(data)
                else:
                    st.error(f"에러 {code}: {data}")


if __name__ == "__main__":
    main()
