# -*- coding: utf-8 -*-
"""
main_api.py 모든 엔드포인트 동작 테스트.
실행 전: 서버 기동 (uvicorn main_api:app --host 127.0.0.1 --port 8000)
  - 로컬 확인 시 반드시 최신 코드로 서버 재시작 후 테스트 (invoke/batch 등 라우트 반영)
환경변수: OPENAI_API_KEY (LLM 사용 엔드포인트 필수), LAW_API_OC (서버에 설정 시 서류 QA 사용)

로컬 전체 테스트: 서버 재시작 후
  python scripts/test_all_endpoints.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import httpx

BASE_URL = os.getenv("LAW_API_BASE_URL", "http://127.0.0.1:8000")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
TIMEOUT = 90.0


def ok(name: str, res: httpx.Response, body: dict = None) -> bool:
    if res.status_code == 200:
        print(f"  [OK] {name}: 200")
        return True
    msg = body.get("message", res.text[:200]) if isinstance(body, dict) else (res.text[:200] if res.text else "")
    print(f"  [FAIL] {name}: {res.status_code} - {msg}")
    return False


def run():
    failed = []
    with httpx.Client(timeout=TIMEOUT) as client:
        # --- GET ---
        print("\n--- GET / ---")
        res = client.get(f"{BASE_URL}/")
        body = res.json() if res.status_code == 200 else None
        if not ok("GET /", res, body):
            failed.append("GET /")

        print("\n--- GET /api/v1/health ---")
        res = client.get(f"{BASE_URL}/api/v1/health")
        body = res.json() if res.status_code == 200 else None
        if not ok("GET /api/v1/health", res, body):
            failed.append("GET /api/v1/health")

        if not OPENAI_KEY:
            print("\n[WARN] OPENAI_API_KEY 없음. LLM 엔드포인트는 400 예상. 나머지만 검사합니다.")

        # --- POST (LLM 필요) ---
        def post_llm(path: str, json_body: dict) -> tuple:
            if OPENAI_KEY:
                json_body = {**json_body, "openai_api_key": OPENAI_KEY}
            res = client.post(f"{BASE_URL}{path}", json=json_body)
            try:
                body = res.json()
            except Exception:
                body = {}
            return res, body

        print("\n--- POST /api/v1/chat/route ---")
        res, body = post_llm("/api/v1/chat/route", {"text": "퇴직금을 못 받았어요"})
        if res.status_code != 200 and not OPENAI_KEY and body.get("code") == "MISSING_API_KEY":
            print("  [SKIP] OPENAI_API_KEY 없음으로 400 (예상)")
        elif not ok("POST /api/v1/chat/route", res, body):
            failed.append("POST /api/v1/chat/route")

        print("\n--- POST /api/v1/chat/classify ---")
        res, body = post_llm("/api/v1/chat/classify", {
            "situation": "2년 동안 카페에서 일했는데 퇴직금을 못 받고 해고당했어요.",
            "top_k": 3,
        })
        if res.status_code != 200 and not OPENAI_KEY and body.get("code") == "MISSING_API_KEY":
            print("  [SKIP] OPENAI_API_KEY 없음으로 400 (예상)")
        elif not ok("POST /api/v1/chat/classify", res, body):
            failed.append("POST /api/v1/chat/classify")
        else:
            issues = (body or {}).get("issues") or []
            if issues:
                selected_issue = issues[0]
                print("\n--- POST /api/v1/chat/checklist ---")
                res2, body2 = post_llm("/api/v1/chat/checklist", {
                    "issue": selected_issue,
                    "situation": "2년 동안 카페에서 일했는데 퇴직금을 못 받고 해고당했어요.",
                    "all_qa": [],
                })
                if not ok("POST /api/v1/chat/checklist", res2, body2):
                    failed.append("POST /api/v1/chat/checklist")
                else:
                    checklist = (body2 or {}).get("checklist") or []
                    all_qa = [{"question": (x.get("question") or x.get("item") or ""), "answer": "네"} for x in checklist[:2]]
                    print("\n--- POST /api/v1/chat/conclusion ---")
                    res3, body3 = post_llm("/api/v1/chat/conclusion", {
                        "issue": selected_issue,
                        "all_qa": all_qa,
                        "stream": False,
                    })
                    if not ok("POST /api/v1/chat/conclusion", res3, body3):
                        failed.append("POST /api/v1/chat/conclusion")

        print("\n--- POST /api/v1/chat/invoke ---")
        res, body = post_llm("/api/v1/chat/invoke", {
            "message": "월급을 두 달째 못 받았어요",
            "thread_id": "test-all-endpoints",
        })
        if res.status_code != 200 and not OPENAI_KEY and body.get("code") == "MISSING_API_KEY":
            print("  [SKIP] OPENAI_API_KEY 없음으로 400 (예상)")
        elif not ok("POST /api/v1/chat/invoke", res, body):
            failed.append("POST /api/v1/chat/invoke")

        print("\n--- POST /api/v1/chat/invoke/batch ---")
        res, body = post_llm("/api/v1/chat/invoke/batch", {
            "requests": [{"message": "퇴직금 계산해 주세요", "thread_id": "batch-1"}],
        })
        if res.status_code != 200 and not OPENAI_KEY and body.get("code") == "MISSING_API_KEY":
            print("  [SKIP] OPENAI_API_KEY 없음으로 400 (예상)")
        elif not ok("POST /api/v1/chat/invoke/batch", res, body):
            failed.append("POST /api/v1/chat/invoke/batch")

        print("\n--- POST /api/v1/chat/qa/knowledge ---")
        res, body = post_llm("/api/v1/chat/qa/knowledge", {"question": "퇴직금 분할 약정이 유효한가요?"})
        if res.status_code != 200 and not OPENAI_KEY and body.get("code") == "MISSING_API_KEY":
            print("  [SKIP] OPENAI_API_KEY 없음으로 400 (예상)")
        elif not ok("POST /api/v1/chat/qa/knowledge", res, body):
            failed.append("POST /api/v1/chat/qa/knowledge")

        print("\n--- POST /api/v1/chat/qa/calculation ---")
        res, body = post_llm("/api/v1/chat/qa/calculation", {
            "question": "평균임금 20만원, 근속 2년인 경우 퇴직금은 얼마인가요?",
        })
        if res.status_code != 200 and not OPENAI_KEY and body.get("code") == "MISSING_API_KEY":
            print("  [SKIP] OPENAI_API_KEY 없음으로 400 (예상)")
        elif not ok("POST /api/v1/chat/qa/calculation", res, body):
            failed.append("POST /api/v1/chat/qa/calculation")

        print("\n--- POST /api/v1/chat/qa/documents ---")
        res = client.post(f"{BASE_URL}/api/v1/chat/qa/documents", json={"question": "해고예보 서식"})
        try:
            body = res.json()
        except Exception:
            body = {}
        if res.status_code == 400 and body.get("code") == "DOCUMENTS_REQUIRES_LAW_API_KEY":
            print("  [SKIP] 서버 LAW_API_OC 미설정으로 400 (선택)")
        elif not ok("POST /api/v1/chat/qa/documents", res, body):
            failed.append("POST /api/v1/chat/qa/documents")

        # --- Law browsing ---
        print("\n--- GET /api/v1/laws/list ---")
        res = client.get(f"{BASE_URL}/api/v1/laws/list")
        body = res.json() if res.status_code == 200 else None
        if not ok("GET /api/v1/laws/list", res, body):
            failed.append("GET /api/v1/laws/list")
        else:
            laws = body if isinstance(body, list) else (body.get("data") or body.get("laws") or [])
            if laws and isinstance(laws, list) and len(laws) > 0:
                first = laws[0] if isinstance(laws[0], dict) else {}
                law_id = first.get("id") or first.get("law_id")
                source = first.get("source")
                print("\n--- GET /api/v1/laws/chapters ---")
                res = client.get(f"{BASE_URL}/api/v1/laws/chapters", params={"law_id": law_id, "source": source or ""})
                b2 = res.json() if res.status_code == 200 else None
                if not ok("GET /api/v1/laws/chapters", res, b2):
                    failed.append("GET /api/v1/laws/chapters")
                else:
                    ch_list = b2 if isinstance(b2, list) else (b2.get("chapters") or [])
                    if ch_list and len(ch_list) > 0:
                        ch_num = ch_list[0].get("chapter_number") or ch_list[0].get("number") or "1"
                        print("\n--- GET /api/v1/laws/articles/{chapter_number} ---")
                        res = client.get(f"{BASE_URL}/api/v1/laws/articles/{ch_num}", params={"law_id": law_id, "source": source or ""})
                        if not ok("GET /api/v1/laws/articles/{chapter_number}", res, res.json() if res.status_code == 200 else None):
                            failed.append("GET /api/v1/laws/articles/{chapter_number}")

    print("\n" + "=" * 60)
    if failed:
        print(f"[FAIL] 실패: {len(failed)}개 - {failed}")
        return 1
    print("[OK] 모든 호출 통과 (또는 예상된 400)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
