# -*- coding: utf-8 -*-
"""
체크리스트 개선 검증: API로 1차·2차 호출 후 다음을 확인합니다.
1) 같은 질문이 2차에 반복되지 않는지
2) 사용자 질문에 이미 있는 정보(예: 근속 7개월)를 다시 묻지 않는지
3) 전제가 맞는지 먼저 묻는지(예: 조사받은 적 있나요? → 보호 조치 받았나요?)

실행 전: 서버 기동 (uvicorn main_api:app --host 127.0.0.1 --port 8000)
환경변수: OPENAI_API_KEY

  python scripts/test_checklist_improvements.py
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

SITUATION = "중소기업에 다니고 있고 근속 7개월 차인데, 다음 달에 육아휴직을 쓸 수 있나요? 급여는 얼마나 나오죠?"


def main():
    if not OPENAI_KEY:
        print("OPENAI_API_KEY가 없습니다. .env 또는 환경변수로 설정 후 실행하세요.")
        return 1

    with httpx.Client(timeout=TIMEOUT) as client:
        # 1) classify
        print("1) POST /api/v1/chat/classify ...")
        res = client.post(f"{BASE_URL}/api/v1/chat/classify", json={
            "situation": SITUATION,
            "openai_api_key": OPENAI_KEY,
        })
        if res.status_code != 200:
            print(f"  classify 실패: {res.status_code} - {res.text[:300]}")
            return 1
        data = res.json()
        issue = data.get("selected_issue") or (data.get("issues") or [""])[0]
        print(f"  selected_issue: {issue}")

        # 2) checklist 1차 (situation 포함 → 이미 말한 '7개월' 반영되어야 함)
        print("\n2) POST /api/v1/chat/checklist (1차, all_qa=[]) ...")
        res2 = client.post(f"{BASE_URL}/api/v1/chat/checklist", json={
            "issue": issue,
            "situation": SITUATION,
            "all_qa": [],
            "openai_api_key": OPENAI_KEY,
        })
        if res2.status_code != 200:
            print(f"  checklist 실패: {res2.status_code} - {res2.text[:300]}")
            return 1
        data2 = res2.json()
        checklist1 = data2.get("checklist") or []
        print(f"  1차 체크리스트 {len(checklist1)}개:")
        for i, item in enumerate(checklist1, 1):
            q = item.get("question", item.get("item", ""))
            print(f"    {i}. {q}")

        # 검증: "1년 이상" / "근속 기간" 질문이 있으면 경고 (사용자가 이미 7개월이라고 함)
        redundant = [q for item in checklist1 for q in [item.get("question", "")] if q and ("1년 이상" in q or ("근속" in q and "1년" in q))]
        if redundant:
            print("\n  [경고] 사용자가 이미 '근속 7개월'이라고 했는데 다음 질문이 있음:", redundant)
        else:
            print("\n  [OK] '1년 이상 근속?' 유형의 중복 질문 없음")

        # 3) 2차 시뮬레이션: 1차 항목에 모두 "네"로 답한 뒤 checklist 다시 요청
        all_qa = [{"question": item.get("question", item.get("item", "")), "answer": "네"} for item in checklist1]
        if all_qa:
            print("\n3) POST /api/v1/chat/checklist (2차, all_qa=1차 답변) ...")
            res3 = client.post(f"{BASE_URL}/api/v1/chat/checklist", json={
                "issue": issue,
                "situation": SITUATION,
                "all_qa": all_qa,
                "previous_rag_results": data2.get("rag_results", [])[:5],
                "openai_api_key": OPENAI_KEY,
            })
            if res3.status_code == 200:
                data3 = res3.json()
                checklist2 = data3.get("checklist") or []
                print(f"  2차 체크리스트 {len(checklist2)}개:")
                for i, item in enumerate(checklist2, 1):
                    q = item.get("question", item.get("item", ""))
                    print(f"    {i}. {q}")
                # 1차와 동일한 질문이 2차에 있으면 경고
                q1_set = {item.get("question", item.get("item", "")).strip() for item in checklist1}
                dup = [item.get("question", item.get("item", "")) for item in checklist2 if item.get("question", item.get("item", "")).strip() in q1_set]
                if dup:
                    print("\n  [경고] 1차와 동일한 질문이 2차에 반복됨:", dup[:3])
                else:
                    print("\n  [OK] 1차와 동일한 질문 반복 없음")
            else:
                print(f"  2차 checklist 실패: {res3.status_code}")

    print("\n검증 스크립트 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
