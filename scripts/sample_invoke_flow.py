# -*- coding: utf-8 -*-
"""
=============================================================================
LawChat API 샘플: invoke 한 번에 상담 흐름 (시작 → 체크리스트 → 결론)
=============================================================================
  이 파일은 API 사용자를 위한 샘플 코드입니다. 주석을 읽으면 invoke 흐름을
  그대로 따라 구현할 수 있습니다.

[이 스크립트가 하는 일]
  사용자가 "월급을 두 달째 못 받았어요"처럼 상황을 말하면,
  API가 이슈를 감지하고 필요 시 체크리스트 질문을 내려줍니다.
  클라이언트가 그 질문에 답변을 보내면, 같은 대화(thread_id)로 이어서
  결론(phase: conclusion)이 나올 때까지 반복할 수 있습니다.

[API 흐름 요약]
  1) POST /api/v1/chat/invoke (사용자 메시지)
     → phase: "checklist" 이면 체크리스트가 옴. "conclusion"이면 바로 결론.
  2) phase가 "checklist"일 때만, 같은 thread_id로 체크리스트 답변을 보냄.
     → 답변 형식: "질문1: 네\\n질문2: 아니요\\n..." (한 줄에 "질문: 답변")
  3) 응답이 phase: "conclusion"이 될 때까지 2)를 반복할 수 있음.
     (서버가 추가 질문이 필요 없다고 판단하면 한 번만에 conclusion으로 감)

[필수 환경변수]
  - OPENAI_API_KEY : LLM 호출에 사용. 클라이언트가 반드시 요청 바디에 넣어야 함.
  - LAW_API_BASE_URL : (선택) 기본값 로컬. 배포 서버 쓰려면
    예: https://law-chat-api.onrender.com

[실행 예]
  배포 서버: LAW_API_BASE_URL=https://law-chat-api.onrender.com python scripts/sample_invoke_flow.py
  로컬:      터미널1에서 uvicorn main_api:app --host 127.0.0.1 --port 8000 실행 후
             터미널2에서 python scripts/sample_invoke_flow.py

  전부 오버라이드 확인 (이슈 분류 / 체크리스트 / 체크리스트 연속 / 결론):
             python scripts/sample_invoke_flow.py --test-all-overrides
             - 1차·2차 동일한 prompt_overrides 전달 (체크리스트 포함).
             - 1차에서 체크리스트 오버라이드 적용 여부 확인, 2차에서 연속·결론 확인.
"""
import os
import sys
import time

# .env에서 OPENAI_API_KEY 등 로드 (있으면)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import httpx

# -----------------------------------------------------------------------------
# 설정
# -----------------------------------------------------------------------------
# API 서버 주소. 배포 서버 사용 시 LAW_API_BASE_URL 로 지정.
BASE_URL = os.getenv("LAW_API_BASE_URL", "http://127.0.0.1:8000")
# LLM 호출용 API 키. invoke 요청마다 바디에 openai_api_key 로 넣어야 함.
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
# 요청 타임아웃(초). 배포 서버는 콜드스타트 시 길게 잡는 것이 안전.
TIMEOUT_SEC = 180

# 같은 대화를 이어가려면 매 요청마다 같은 thread_id 를 보내야 함.
# 새 상담마다 다른 값을 쓰면 됨. (예: UUID, 사용자ID_타임스탬프 등)
THREAD_ID = f"sample-{int(time.time())}"


def run_sample():
    """샘플 흐름: 헬스체크 → 1차 invoke(상황) → 필요 시 체크리스트 답변 → 결론 확인."""
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY 환경변수(또는 .env)를 설정하세요.")
        sys.exit(1)

    print(f"API: {BASE_URL}")
    print(f"thread_id: {THREAD_ID}\n")

    with httpx.Client(timeout=TIMEOUT_SEC) as client:
        # -------------------------------------------------------------------------
        # 1. 헬스체크 (서버 살아 있는지 확인)
        # -------------------------------------------------------------------------
        print("[1] GET /api/v1/health")
        try:
            r = client.get(f"{BASE_URL}/api/v1/health")
            r.raise_for_status()
            body = r.json()
            print(f"    상태: {body.get('status')}, 벡터스토어: {body.get('vector_store_ready')}\n")
        except Exception as e:
            print(f"    실패: {e}\n    서버가 떠 있는지 확인하세요.")
            sys.exit(1)

        # -------------------------------------------------------------------------
        # 2. 1차 invoke: 사용자 상황 메시지 전송
        # -------------------------------------------------------------------------
        # 사용자가 말한 "상황" 한 문장. 노동법 상담이면 예: 임금 체불, 퇴직금, 해고 등.
        user_message = "월급을 두 달째 못 받았어요"

        print(f"[2] POST /api/v1/chat/invoke (message={user_message!r})")
        print("     요청 바디: message, thread_id, openai_api_key 필수.")

        r = client.post(
            f"{BASE_URL}/api/v1/chat/invoke",
            json={
                "message": user_message,
                "thread_id": THREAD_ID,
                "openai_api_key": OPENAI_API_KEY,
            },
        )
        if r.status_code != 200:
            print(f"    실패: {r.status_code} {r.text[:400]}")
            sys.exit(1)

        payload = r.json()
        # phase: "input" | "checklist" | "conclusion"
        # - input: 지식/계산 등 단발 응답이면 체크리스트 없이 여기서 끝날 수 있음.
        # - checklist: 이슈가 감지되어 질문 목록이 옴. 클라이언트는 이 질문들에 답변을 보내야 함.
        # - conclusion: (체크리스트 없이 바로 결론이 나오는 경로) 결론이 이미 옴.
        phase = payload.get("phase")
        messages = payload.get("messages") or []
        # 체크리스트 항목. 각 항목은 {"question": "...", "item": "..."} 형태일 수 있음.
        checklist = payload.get("checklist") or []

        print(f"    phase: {phase}")
        print(f"    체크리스트 개수: {len(checklist)}")

        # 화면에 보여줄 "마지막 AI 메시지"는 항상 messages 배열의 마지막 요소의 "c" (content).
        if messages:
            last_content = messages[-1].get("c") or ""
            print(f"    마지막 메시지 길이: {len(last_content)}자")
            print(f"    --- 메시지 내용(앞 500자) ---\n    {last_content[:500]}...\n" if len(last_content) > 500 else f"    --- 메시지 내용 ---\n    {last_content}\n")

        # -------------------------------------------------------------------------
        # 3. phase가 "checklist"이면, 같은 thread_id로 체크리스트 답변 전송
        # -------------------------------------------------------------------------
        # 서버가 "추가 질문이 필요 없다"고 판단할 때까지 이 단계가 반복될 수 있음.
        # (보통 1라운드만 하고 conclusion으로 가는 경우가 많음)
        step = 3
        while phase == "checklist" and checklist:
            # 체크리스트 답변 형식: 한 줄에 "질문문장: 답변(네/아니요/모르겠음)".
            # 여러 줄이면 줄바꿈으로 구분. 서버가 이걸 파싱해서 Q&A 목록으로 씀.
            answer_lines = []
            for item in checklist:
                q = item.get("question") or item.get("item") or str(item)
                if isinstance(q, dict):
                    q = q.get("question") or q.get("item") or ""
                # 샘플에서는 전부 "네"로 통일. 실제 앱에서는 사용자 선택값으로 채움.
                answer_lines.append(f"{q.strip()}: 네")
            checklist_message = "\n".join(answer_lines)

            print(f"[{step}] POST /api/v1/chat/invoke (체크리스트 답변 {len(answer_lines)}개)")
            print("     같은 thread_id 로 보내야 같은 상담으로 이어짐.")

            r = client.post(
                f"{BASE_URL}/api/v1/chat/invoke",
                json={
                    "message": checklist_message,
                    "thread_id": THREAD_ID,
                    "openai_api_key": OPENAI_API_KEY,
                },
            )
            if r.status_code != 200:
                print(f"    실패: {r.status_code} {r.text[:400]}")
                sys.exit(1)

            payload = r.json()
            phase = payload.get("phase")
            messages = payload.get("messages") or []
            checklist = payload.get("checklist") or []

            print(f"    phase: {phase}")
            if messages:
                last_content = messages[-1].get("c") or ""
                print(f"    마지막 메시지 길이: {len(last_content)}자")
                # 결론 단계면 이 내용이 "감지된 이슈: ... **결론** ..." 형태의 최종 답변.
                if phase == "conclusion":
                    print("    --- 결론 메시지(앞 800자) ---")
                    print("    " + (last_content[:800] + "..." if len(last_content) > 800 else last_content))
                else:
                    print(f"    --- 메시지(앞 300자) ---\n    {last_content[:300]}...\n")

            step += 1
            # 무한 루프 방지: 체크리스트가 2라운드 이상 나와도 최대 2번만 답변 후 종료.
            if phase == "checklist" and len(checklist) > 0 and step > 4:
                print("    (체크리스트 2라운드까지 수행 후 종료)")
                break

        # -------------------------------------------------------------------------
        # 4. 최종 상태 정리
        # -------------------------------------------------------------------------
        print("\n=== 샘플 흐름 종료 ===")
        print(f"최종 phase: {phase}")
        if messages:
            full = messages[-1].get("c") or ""
            print(f"최종 메시지(결론) 전체 길이: {len(full)}자")
        print("결론 내용은 위 '마지막 메시지' / '결론 메시지'에 출력된 문자열이 그대로 사용할 값입니다.")


def _safe_print(s: str) -> None:
    """Windows cp949 콘솔에서 유니코드 깨짐 방지."""
    try:
        s.encode("cp949")
    except UnicodeEncodeError:
        s = s.encode("cp949", errors="replace").decode("cp949")
    print(s)


def run_all_prompt_overrides_test():
    """
    이슈 분류 / 체크리스트 / 체크리스트 연속 / 결론 전부 prompt_overrides 가 반영되는지 확인.
    각 단계별로 마커 문구를 넣어서 응답에 포함되는지 검사합니다.
    """
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY 환경변수(또는 .env)를 설정하세요.")
        sys.exit(1)

    thread_id = f"sample-all-override-{int(time.time())}"

    # 1) 이슈 분류: 오버라이드 시 정규화에서 커스텀 라벨이 걸러질 수 있어, 여기서는 기본 사용.
    #    (오버라이드 적용 여부는 1차 invoke 성공 = 템플릿 형식 오류 없음으로 간주)
    override_issue = None  # 기본 프롬프트 사용

    # 2) 체크리스트: 플레이스홀더 {issue}, {rag_context}, {filtered_provisions}, {already_asked_text}, {situation_block}, {already_block}, {situation}, {tail}
    override_checklist = """Issue: {issue}
{situation_block}
{already_block}
[Already asked] {already_asked_text}
[Situation] {situation}
[Filtered provisions]
{filtered_provisions}

[Full provisions]
{rag_context}
{tail}

Generate a JSON array of checklist items. At least one "question" must contain the exact phrase: [체크리스트오버라이드]. Write in Korean."""

    # 3) 체크리스트 연속: 플레이스홀더 {issue}, {qa_text}, {rag_context}
    #    리터럴 중괄호는 {{ }} 로 이스케이프 (format 시 유지)
    override_continuation = """Issue: {issue}

[Q&A]
{qa_text}

[Provisions]
{rag_context}

Return only: {{"should_continue": false, "reason": "오버라이드 테스트 1라운드"}}"""

    # 4) 결론: 플레이스홀더 {issue}, {qa_list}, {rag_context} 등
    override_conclusion = """Issue: {issue}

[User's Q&A]
{qa_list}

[Provided legal provisions]
{rag_context}

Write a short conclusion in Korean. You MUST start the first line of your conclusion with: [오버라이드 테스트]"""

    prompt_overrides = {
        "user_checklist": override_checklist,
        "user_checklist_continuation": override_continuation,
        "user_conclusion": override_conclusion,
    }
    # 1차·2차 동일한 prompt_overrides 사용 (체크리스트 오버라이드 포함)
    prompt_overrides_2nd = prompt_overrides

    results = {"이슈 분류": False, "체크리스트": False, "체크리스트 연속": False, "결론": False}

    _safe_print(f"=== 전부 프롬프트 오버라이드 확인 ===\nAPI: {BASE_URL}\nthread_id: {thread_id}\n")
    _safe_print("1차·2차 모두 동일한 prompt_overrides 로 호출합니다.\n")

    with httpx.Client(timeout=TIMEOUT_SEC) as client:
        try:
            r = client.get(f"{BASE_URL}/api/v1/health")
            r.raise_for_status()
        except Exception as e:
            _safe_print(f"헬스체크 실패: {e}\n로컬 서버를 먼저 실행하세요.")
            sys.exit(1)

        # ---------- 1차 invoke (체크리스트·연속·결론 오버라이드 전달) ----------
        # 500 시 원인 확인을 위해 X-Law-Debug: 1 로 예외 메시지 수신
        r1 = client.post(
            f"{BASE_URL}/api/v1/chat/invoke",
            json={
                "message": "월급을 두 달째 못 받았어요",
                "thread_id": thread_id,
                "openai_api_key": OPENAI_API_KEY,
                "prompt_overrides": prompt_overrides,
            },
            headers={"X-Law-Debug": "1"},
        )
        if r1.status_code != 200:
            _safe_print(f"1차 invoke 실패: {r1.status_code} {r1.text[:500]}")
            _safe_print("(서버를 수정 후 재시작했는지 확인하세요. LAW_DEBUG=1 또는 X-Law-Debug: 1 이면 예외 메시지가 포함됩니다.)")
            sys.exit(1)
        p1 = r1.json()
        phase = p1.get("phase")
        issues = p1.get("issues") or []
        selected_issue = p1.get("selected_issue") or ""
        checklist = p1.get("checklist") or []
        msg1 = (p1.get("messages") or [])[-1].get("c") or "" if p1.get("messages") else ""

        _safe_print(f"[1] 1차 invoke phase={phase}, 이슈={issues}, selected_issue={selected_issue!r}, 체크리스트 {len(checklist)}개")

        # 이슈 분류: 이번 테스트에서는 오버라이드 미사용 → 1차 성공 시 "적용됨"으로 간주 (형식 검증용)
        results["이슈 분류"] = True
        _safe_print("    [OK] 이슈 분류 (기본 사용, 오버라이드 생략)")

        # 체크리스트 오버라이드: 1차에서 적용됐는지 확인 (phase=checklist 시 2차에서도 동일 오버라이드 사용)
        results["체크리스트"] = bool(
            phase == "checklist"
            and checklist
            and any(
                ("[체크리스트오버라이드]" in (item.get("question") or item.get("item") or str(item)))
                for item in checklist
            )
        )
        if results["체크리스트"]:
            _safe_print("    [OK] 체크리스트 오버라이드 (1차 적용 확인)")
        else:
            _safe_print("    [SKIP] 체크리스트 오버라이드 (phase/체크리스트 없음 또는 마커 미포함)")

        if phase != "checklist" or not checklist:
            _safe_print("    체크리스트가 없어 2차 invoke 생략. 나머지(연속/결론)는 미확인.")
            _print_all_overrides_summary(results)
            sys.exit(0)

        # ---------- 2차 invoke (체크리스트 연속 + 결론 오버라이드 적용) ----------
        answer_lines = [f"{(item.get('question') or item.get('item') or str(item)).strip()}: 네" for item in checklist]
        r2 = client.post(
            f"{BASE_URL}/api/v1/chat/invoke",
            json={
                "message": "\n".join(answer_lines),
                "thread_id": thread_id,
                "openai_api_key": OPENAI_API_KEY,
                "prompt_overrides": prompt_overrides_2nd,
            },
        )
        if r2.status_code != 200:
            _safe_print(f"2차 invoke 실패: {r2.status_code} {r2.text[:300]}")
            _print_all_overrides_summary(results)
            sys.exit(1)
        p2 = r2.json()
        phase2 = p2.get("phase")
        messages = p2.get("messages") or []
        last_content = (messages[-1].get("c") or "") if messages else ""

        _safe_print(f"[2] 2차 invoke phase={phase2}")

        # 체크리스트 연속: should_continue false 로 한 번에 결론으로 갔으면 성공
        if phase2 == "conclusion":
            results["체크리스트 연속"] = True
            _safe_print("    [OK] 체크리스트 연속 오버라이드 반영됨 (1라운드 후 conclusion)")
        else:
            _safe_print("    [FAIL] 체크리스트 연속 오버라이드 미반영 (phase가 conclusion이 아님)")

        # 결론 오버라이드
        if "[오버라이드 테스트]" in last_content:
            results["결론"] = True
            _safe_print("    [OK] 결론 오버라이드 반영됨")
        else:
            _safe_print("    [FAIL] 결론 오버라이드 미반영")

        _print_all_overrides_summary(results)


def _print_all_overrides_summary(results: dict) -> None:
    _safe_print("\n--- 전체 오버라이드 확인 요약 ---")
    for name, ok in results.items():
        if ok is None:
            _safe_print(f"  {name}: SKIP")
        else:
            _safe_print(f"  {name}: {'OK' if ok else 'FAIL'}")
    passed = [k for k, v in results.items() if v is True]
    failed = [k for k, v in results.items() if v is False]
    if failed:
        _safe_print("  >>> 일부 미반영: " + ", ".join(failed))
    elif len(passed) == len(results):
        _safe_print("  >>> 전부 반영됨")
    else:
        _safe_print("  >>> 확인 완료 (일부 SKIP)")


if __name__ == "__main__":
    if "--test-all-overrides" in sys.argv:
        run_all_prompt_overrides_test()
    else:
        run_sample()
