import json
import os
import requests

BASE_URL = "http://localhost:8000"
TIMEOUT = 90

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")


def load_openai_api_key(env_path: str) -> str:
    if not os.path.exists(env_path):
        raise RuntimeError(f".env not found at {env_path}")
    api_key = None
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("OPENAI_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in .env")
    return api_key


def api_post(session: requests.Session, path: str, body: dict):
    url = f"{BASE_URL}{path}"
    r = session.post(url, json=body, timeout=TIMEOUT)
    try:
        data = r.json()
    except Exception:
        data = {"_raw_text": r.text}
    return r.status_code, data


def main():
    api_key = load_openai_api_key(ENV_PATH)
    session = requests.Session()

    # 테스트 케이스들: 사용자가 이미 명시한 사실을 체크리스트에서 다시 물어보는지 확인
    test_cases = [
        {
            "name": "초과근로 시간 명시",
            "situation": "주당 60시간 넘게 일하는데 추가 수당을 못 받고 있습니다.",
            "should_not_ask": ["60시간", "주당 60", "60시간 넘게"]
        },
        {
            "name": "체불 기간 명시",
            "situation": "월급을 두 달째 못 받았어요.",
            "should_not_ask": ["2개월", "두 달", "2달"]
        },
        {
            "name": "근속 기간 명시",
            "situation": "2년 근무 후 퇴사했는데 퇴직금을 안 준다고 합니다.",
            "should_not_ask": ["2년", "두 해", "24개월"]
        }
    ]

    results = []

    for test_case in test_cases:
        print(f"\n{'='*60}")
        print(f"테스트: {test_case['name']}")
        print(f"상황: {test_case['situation']}")
        print(f"체크리스트에서 물어보면 안 되는 키워드: {test_case['should_not_ask']}")
        print('='*60)

        # 이슈 분류
        body_classify = {
            "situation": test_case["situation"],
            "top_k": 22,
            "openai_api_key": api_key,
        }
        code_c, data_c = api_post(session, "/api/v1/chat/classify", body_classify)
        
        if code_c != 200:
            print(f"이슈 분류 실패: {code_c}")
            continue
        
        issues = data_c.get("issues", [])
        if not issues:
            print("이슈가 없습니다.")
            continue
        
        issue = issues[0]
        print(f"분류된 이슈: {issue}")

        # 체크리스트 생성
        body_checklist = {
            "issue": issue,
            "situation": test_case["situation"],
            "all_qa": [],
            "round": 1,
            "previous_rag_results": [],
            "openai_api_key": api_key,
        }
        code_cl, data_cl = api_post(session, "/api/v1/chat/checklist", body_checklist)
        
        if code_cl != 200:
            print(f"체크리스트 생성 실패: {code_cl}")
            continue

        checklist = data_cl.get("checklist", [])
        questions = [
            (item.get("question") or item.get("item") or str(item))
            for item in checklist
        ]

        print(f"\n생성된 질문 ({len(questions)}개):")
        redundant_found = []
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q}")
            # 이미 명시된 사실을 다시 물어보는지 확인
            for keyword in test_case["should_not_ask"]:
                if keyword in q:
                    redundant_found.append({
                        "question": q,
                        "keyword": keyword
                    })

        if redundant_found:
            print(f"\n[경고] 이미 명시된 사실을 다시 물어본 질문 발견:")
            for item in redundant_found:
                print(f"  - '{item['keyword']}' 포함: {item['question']}")
        else:
            print(f"\n[OK] 이미 명시된 사실을 다시 물어보지 않음")

        results.append({
            "test_case": test_case["name"],
            "situation": test_case["situation"],
            "issue": issue,
            "questions": questions,
            "redundant_found": redundant_found,
            "is_ok": len(redundant_found) == 0
        })

    # 결과 요약
    print(f"\n\n{'='*60}")
    print("전체 테스트 결과 요약")
    print('='*60)
    for r in results:
        status = "[OK]" if r["is_ok"] else "[경고]"
        print(f"{status} {r['test_case']}: {len(r['redundant_found'])}개 중복 질문 발견")

    # 결과 저장
    output_path = os.path.join(ROOT, "situation_redundancy_test.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장됨: {output_path}")


if __name__ == "__main__":
    main()
