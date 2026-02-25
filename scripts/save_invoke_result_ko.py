# -*- coding: utf-8 -*-
"""invoke 흐름 실행 후 한글 결과를 UTF-8 파일로 저장. (결과 보여주기용)"""
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
KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
if not KEY:
    print("OPENAI_API_KEY 없음")
    sys.exit(1)
tid = "show-result-" + str(int(time.time()))
out = []

with httpx.Client(timeout=120) as client:
    r = client.get(BASE + "/api/v1/health")
    if r.status_code != 200:
        print("서버 미동작")
        sys.exit(1)
    r1 = client.post(
        BASE + "/api/v1/chat/invoke",
        json={"message": "월급을 두 달째 못 받았어요", "thread_id": tid, "openai_api_key": KEY},
    )
    if r1.status_code != 200:
        print("invoke1 실패", r1.status_code)
        sys.exit(1)
    p1 = r1.json()
    phase = p1.get("phase")
    msgs = p1.get("messages") or []
    checklist = p1.get("checklist") or []

    out.append("=== 1차 응답 (상황: 월급을 두 달째 못 받았어요) ===")
    out.append("phase: " + str(phase))
    if msgs:
        last_c = msgs[-1].get("c") or ""
        out.append("마지막 메시지 길이: " + str(len(last_c)) + "자")
        out.append("--- 마지막 메시지 전체 ---")
        out.append(last_c)
        out.append("--- 끝 ---")

    if phase == "checklist" and checklist:
        qa_lines = []
        for it in checklist:
            q = it.get("question") or it.get("item") or str(it)
            if isinstance(q, dict):
                q = q.get("question") or q.get("item") or ""
            qa_lines.append(q.strip() + ": 네")
        msg2 = "\n".join(qa_lines)
        r2 = client.post(
            BASE + "/api/v1/chat/invoke",
            json={"message": msg2, "thread_id": tid, "openai_api_key": KEY},
        )
        if r2.status_code != 200:
            out.append("2차 invoke 실패: " + str(r2.status_code))
        else:
            p2 = r2.json()
            phase2 = p2.get("phase")
            msgs2 = p2.get("messages") or []
            concl = p2.get("conclusion") or ""
            out.append("")
            out.append("=== 2차 응답 (체크리스트 답변 후) ===")
            out.append("phase: " + str(phase2))
            if msgs2:
                last_c2 = msgs2[-1].get("c") or ""
                out.append("마지막 메시지 길이: " + str(len(last_c2)) + "자")
                out.append("--- 마지막 메시지 전체 ---")
                out.append(last_c2)
                out.append("--- 끝 ---")
            out.append("conclusion 필드 길이: " + str(len(concl)) + "자")
            if concl:
                out.append("--- conclusion 필드 전체 ---")
                out.append(concl)
                out.append("--- 끝 ---")

result_path = os.path.join(os.path.dirname(__file__), "invoke_result_ko.txt")
with open(result_path, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("저장 완료:", result_path)
