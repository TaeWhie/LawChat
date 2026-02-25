# -*- coding: utf-8 -*-
"""
로컬 API 서버에 대해 invoke로 시작 → 체크리스트(선택) → 결론까지 한 번에 진행.
사용법:
  1. 터미널 1: uvicorn main_api:app --host 127.0.0.1 --port 8000
  2. 터미널 2: python scripts/run_invoke_flow_local.py

환경변수: OPENAI_API_KEY (.env 또는 환경에 설정)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import httpx

BASE = os.getenv("LAW_API_BASE_URL", "http://127.0.0.1:8000")
OPENAI_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
TIMEOUT = 120
THREAD_ID = f"invoke-flow-{int(time.time())}"  # 실행마다 새 스레드로 시작→끝 흐름 검증


def _safe_preview(text, max_len=400):
    """Windows 콘솔(cp949) 출력용: 유니코드 문자를 치환."""
    if not text:
        return ""
    s = (text[:max_len] + "..." if len(text) > max_len else text)
    try:
        s.encode("cp949")
        return s
    except UnicodeEncodeError:
        return s.encode("cp949", errors="replace").decode("cp949")


def main():
    if not OPENAI_KEY:
        print("OPENAI_API_KEY가 없습니다. .env 또는 환경변수를 설정하세요.")
        sys.exit(1)

    print("=== 로컬 invoke 시작 → 끝 흐름 테스트 ===\n")
    print(f"BASE_URL: {BASE}")
    print(f"thread_id: {THREAD_ID}\n")

    with httpx.Client(timeout=TIMEOUT) as client:
        # 헬스체크
        print("[1] GET /api/v1/health ...")
        try:
            r = client.get(f"{BASE}/api/v1/health")
            if r.status_code != 200:
                print(f"  실패: {r.status_code} - 서버를 먼저 띄워 주세요. (uvicorn main_api:app --host 127.0.0.1 --port 8000)")
                sys.exit(1)
            print(f"  OK {r.json()}\n")
        except Exception as e:
            print(f"  연결 실패: {e}. 로컬 서버가 떠 있는지 확인하세요.")
            sys.exit(1)

        # 1차: 상황 메시지
        msg1 = "월급을 두 달째 못 받았어요"
        print(f"[2] POST /api/v1/chat/invoke (message={msg1!r}) ...")
        r = client.post(
            f"{BASE}/api/v1/chat/invoke",
            json={
                "message": msg1,
                "thread_id": THREAD_ID,
                "openai_api_key": OPENAI_KEY,
            },
        )
        if r.status_code != 200:
            print(f"  실패: {r.status_code} - {r.text[:500]}")
            sys.exit(1)
        payload = r.json()
        phase = payload.get("phase")
        messages = payload.get("messages") or []
        checklist = payload.get("checklist") or []
        conclusion = payload.get("conclusion", "")
        print(f"  phase: {phase}")
        print(f"  checklist 개수: {len(checklist)}")
        if messages:
            last = messages[-1]
            full_c = last.get("c") or ""
            c = full_c[:400]
            preview = _safe_preview(c, 400)
            print(f"  마지막 메시지 길이: {len(full_c)}자")
            print(f"  마지막 메시지 미리보기: {preview}...\n" if len(full_c) > 400 else f"  마지막 메시지: {preview}\n")
        if phase == "conclusion" and conclusion:
            print(f"  conclusion 필드 길이: {len(conclusion)}자")
            preview = _safe_preview(conclusion, 300)
            print(f"  conclusion 필드: {preview}...\n" if len(conclusion) > 300 else f"  conclusion 필드: {preview}\n")

        # 체크리스트가 있으면 답변 형식으로 2차 요청
        step = 3
        while phase == "checklist" and checklist:
            answer_lines = []
            for item in checklist:
                q = item.get("question") or item.get("item") or str(item)
                if isinstance(q, dict):
                    q = q.get("question") or q.get("item") or ""
                answer_lines.append(f"{q.strip()}: 네")
            msg2 = "\n".join(answer_lines)
            print(f"[{step}] POST /api/v1/chat/invoke (체크리스트 답변, {len(answer_lines)}개) ...")
            r = client.post(
                f"{BASE}/api/v1/chat/invoke",
                json={
                    "message": msg2,
                    "thread_id": THREAD_ID,
                    "openai_api_key": OPENAI_KEY,
                },
            )
            if r.status_code != 200:
                print(f"  실패: {r.status_code} - {r.text[:500]}")
                sys.exit(1)
            payload = r.json()
            phase = payload.get("phase")
            messages = payload.get("messages") or []
            checklist = payload.get("checklist") or []
            conclusion = payload.get("conclusion", "")
            print(f"  phase: {phase}")
            print(f"  checklist 개수: {len(checklist)}")
            if messages:
                last = messages[-1]
                full_c = last.get("c") or ""
                c = full_c[:400]
                preview = _safe_preview(c, 400)
                print(f"  마지막 메시지 길이: {len(full_c)}자")
                print(f"  마지막 메시지 미리보기: {preview}...\n" if len(full_c) > 400 else f"  마지막 메시지: {preview}\n")
            if phase == "conclusion" and conclusion:
                print(f"  conclusion 필드 길이: {len(conclusion)}자")
                preview = _safe_preview(conclusion, 300)
                print(f"  conclusion 필드: {preview}...\n" if len(conclusion) > 300 else f"  conclusion 필드: {preview}\n")
            step += 1
            if phase == "checklist" and len(checklist) > 0 and step > 4:
                print("  (체크리스트 2라운드까지 진행 후 종료)")
                break

        print("=== 흐름 테스트 완료 ===")
        print(f"최종 phase: {phase}")
        if messages:
            full_c = (messages[-1].get("c") or "")
            print(f"마지막 메시지 전체 길이: {len(full_c)}자")
        if conclusion:
            print(f"conclusion 필드 길이: {len(conclusion)}자")
        else:
            print("conclusion 필드: (비어 있음)" if phase == "conclusion" else "conclusion 필드: (해당 없음)")


if __name__ == "__main__":
    main()
