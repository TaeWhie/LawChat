"""
배포된 LawChat API 각 엔드포인트 동작 검사.
사용: python scripts/check_deployed_api.py
BASE_URL을 변경하면 다른 서버 대상으로 실행 가능.
프로젝트 루트 .env 의 OPENAI_API_KEY 를 자동 로드해 LLM API까지 검사합니다.
"""
import httpx
import json
import os
import sys

# 프로젝트 루트 .env 로드 (OPENAI_API_KEY로 LLM API 검사)
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except Exception:
    pass

BASE_URL = os.getenv("LAW_API_BASE_URL", "https://law-chat-api.onrender.com")
TIMEOUT = 90.0  # invoke 등 LLM 호출은 오래 걸릴 수 있음
# LLM 사용 API는 클라이언트가 openai_api_key를 보내야 함 (서버에 키 설정 불필요)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
# 검사 후 주요 엔드포인트 응답 예시를 출력할지 (True 권장)
SHOW_SAMPLE_RESPONSES = True


def _llm_body(**kwargs):
    """LLM 엔드포인트 요청 바디: openai_api_key(env), model(선택) 추가."""
    body = dict(kwargs)
    if OPENAI_API_KEY:
        body["openai_api_key"] = OPENAI_API_KEY
        body.setdefault("model", os.getenv("LAW_CHAT_MODEL", "gpt-4o-mini"))
    return body

def ok(status: int) -> bool:
    return 200 <= status < 300

def run():
    results = []
    samples = {}  # 엔드포인트별 응답 예시 저장
    if not OPENAI_API_KEY:
        print("(OPENAI_API_KEY 미설정: LLM 사용 API는 400 예상. .env 또는 환경변수로 키 설정 후 실행하면 전체 검사 가능)\n")
    with httpx.Client(timeout=TIMEOUT) as client:
        # GET /
        try:
            res = client.get(f"{BASE_URL}/")
            results.append(("GET /", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
            if res.status_code == 200 and res.text:
                try:
                    samples["GET /"] = json.loads(res.text)
                except Exception:
                    samples["GET /"] = res.text[:500]
        except Exception as e:
            results.append(("GET /", 0, False, str(e)[:80]))

        # GET /api/v1/health
        try:
            res = client.get(f"{BASE_URL}/api/v1/health")
            results.append(("GET /api/v1/health", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
            if res.status_code == 200 and res.text:
                try:
                    samples["GET /api/v1/health"] = json.loads(res.text)
                except Exception:
                    samples["GET /api/v1/health"] = res.text[:500]
        except Exception as e:
            results.append(("GET /api/v1/health", 0, False, str(e)[:80]))

        # GET /api/v1/laws/list
        try:
            res = client.get(f"{BASE_URL}/api/v1/laws/list")
            results.append(("GET /api/v1/laws/list", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("GET /api/v1/laws/list", 0, False, str(e)[:80]))

        # GET /api/v1/laws/chapters (no params)
        try:
            res = client.get(f"{BASE_URL}/api/v1/laws/chapters")
            results.append(("GET /api/v1/laws/chapters", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("GET /api/v1/laws/chapters", 0, False, str(e)[:80]))

        # POST /api/v1/chat/route (LLM 사용 → openai_api_key 필수)
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/route", json=_llm_body(text="퇴직금을 못 받았어요"))
            results.append(("POST /api/v1/chat/route", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("POST /api/v1/chat/route", 0, False, str(e)[:80]))

        # POST /api/v1/chat/invoke (LLM 사용 → openai_api_key 필수)
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/invoke", json=_llm_body(message="퇴직금이 뭐예요?"))
            results.append(("POST /api/v1/chat/invoke", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
            if res.status_code == 200 and res.text and len(res.text) < 8000:
                try:
                    data = json.loads(res.text)
                    # 메시지 내용만 요약해서 저장 (전체는 길 수 있음)
                    if "messages" in data and isinstance(data["messages"], list):
                        msg_preview = [{"t": m.get("t"), "c": (m.get("c") or "")[:120] + "..." if len(str(m.get("c") or "")) > 120 else m.get("c")} for m in data["messages"][:3]]
                        samples["POST /api/v1/chat/invoke"] = {"status": data.get("status"), "phase": data.get("phase"), "messages_preview": msg_preview}
                    else:
                        samples["POST /api/v1/chat/invoke"] = data
                except Exception:
                    samples["POST /api/v1/chat/invoke"] = res.text[:800]
        except Exception as e:
            results.append(("POST /api/v1/chat/invoke", 0, False, str(e)[:80]))

        # POST /api/v1/chat/classify (LLM 사용 → openai_api_key 필수)
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/classify", json=_llm_body(situation="2년 일했는데 퇴직금을 못 받았어요."))
            results.append(("POST /api/v1/chat/classify", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
            if res.status_code == 200 and res.text:
                try:
                    samples["POST /api/v1/chat/classify"] = json.loads(res.text)
                except Exception:
                    samples["POST /api/v1/chat/classify"] = res.text[:600]
        except Exception as e:
            results.append(("POST /api/v1/chat/classify", 0, False, str(e)[:80]))

        # POST /api/v1/chat/checklist (LLM 사용 → openai_api_key 필수)
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/checklist", json=_llm_body(
                issue="퇴직금",
                situation="2년 일했는데 퇴직금을 못 받았어요.",
                all_qa=[],
            ))
            results.append(("POST /api/v1/chat/checklist", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("POST /api/v1/chat/checklist", 0, False, str(e)[:80]))

        # POST /api/v1/chat/conclusion (LLM 사용 → openai_api_key 필수)
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/conclusion", json=_llm_body(
                issue="퇴직금",
                all_qa=[{"question": "1년 이상 근무했나요?", "answer": "네"}],
                stream=False,
            ))
            results.append(("POST /api/v1/chat/conclusion", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("POST /api/v1/chat/conclusion", 0, False, str(e)[:80]))

        # POST /api/v1/chat/qa/knowledge (LLM 사용 → openai_api_key 필수)
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/qa/knowledge", json=_llm_body(question="퇴직금이란?"))
            results.append(("POST /api/v1/chat/qa/knowledge", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("POST /api/v1/chat/qa/knowledge", 0, False, str(e)[:80]))

        # POST /api/v1/chat/qa/calculation (LLM 사용 → openai_api_key 필수)
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/qa/calculation", json=_llm_body(question="퇴직금 계산 방법 알려줘요"))
            results.append(("POST /api/v1/chat/qa/calculation", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("POST /api/v1/chat/qa/calculation", 0, False, str(e)[:80]))

        # POST /api/v1/chat/qa/documents
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/qa/documents", json={"question": "해고예보 서식"})
            results.append(("POST /api/v1/chat/qa/documents", res.status_code, ok(res.status_code), res.text[:80] if res.text else ""))
        except Exception as e:
            results.append(("POST /api/v1/chat/qa/documents", 0, False, str(e)[:80]))

    # 리포트
    print(f"\n=== LawChat API 검사: {BASE_URL} ===\n")
    passed = sum(1 for r in results if r[2])
    failed = sum(1 for r in results if not r[2])
    for r in results:
        name, code, ok_ = r[0], r[1], r[2]
        status = "OK" if ok_ else "FAIL"
        print(f"  [{status}] {name}  ->  {code}")
    print(f"\n  통과: {passed} / 실패: {failed} / 전체: {len(results)}")
    if failed > 0:
        print("\n실패한 항목 상세:")
        for r in results:
            if not r[2]:
                print(f"  - {r[0]}: {r[1]}  {r[3]}")

    if SHOW_SAMPLE_RESPONSES and samples:
        print("\n" + "=" * 60)
        print("  [응답 예시] (주요 엔드포인트)")
        print("=" * 60)
        for name, body in samples.items():
            print(f"\n--- {name} ---")
            if isinstance(body, dict):
                print(json.dumps(body, ensure_ascii=False, indent=2))
            else:
                print(body)
        print("\n" + "=" * 60)
    print()
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    # Windows 콘솔 한글 출력
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(run())
