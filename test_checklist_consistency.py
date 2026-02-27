import json
import os
import requests

BASE_URL = "http://localhost:8000"  # 로컬 서버
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

    # 테스트 상황: 주 60시간 초과근로 수당 미지급
    situation = "주당 60시간 넘게 일하는데 추가 수당을 못 받고 있습니다."
    issue = "임금"  # 이슈 분류 결과를 미리 알고 있다고 가정

    print(f"테스트 상황: {situation}")
    print(f"이슈: {issue}")
    print("\n같은 상황으로 체크리스트를 3번 생성합니다...\n")

    results = []

    for i in range(3):
        print(f"[시도 {i+1}/3] 체크리스트 생성 중...")
        body = {
            "issue": issue,
            "situation": situation,
            "all_qa": [],
            "round": 1,
            "previous_rag_results": [],
            "openai_api_key": api_key,
        }
        code, data = api_post(session, "/api/v1/chat/checklist", body)
        if code == 200:
            checklist = data.get("checklist", [])
            questions = [
                (item.get("question") or item.get("item") or str(item))
                for item in checklist
            ]
            results.append({
                "attempt": i + 1,
                "num_questions": len(questions),
                "questions": questions,
                "should_continue": data.get("should_continue"),
            })
            print(f"  [OK] 질문 {len(questions)}개 생성됨")
        else:
            print(f"  [ERROR] 에러 {code}: {data}")
            results.append({"attempt": i + 1, "error": data})

    print("\n" + "=" * 60)
    print("결과 비교:")
    print("=" * 60)

    # 질문 개수 비교
    num_questions = [r.get("num_questions", 0) for r in results if "num_questions" in r]
    if num_questions:
        print(f"\n질문 개수: {num_questions}")
        if len(set(num_questions)) == 1:
            print("[OK] 질문 개수 일관됨")
        else:
            print("[DIFF] 질문 개수가 다름!")

    # 질문 내용 비교
    all_questions = [r.get("questions", []) for r in results if "questions" in r]
    if len(all_questions) >= 2:
        print("\n질문 내용 비교:")
        for i, q_list in enumerate(all_questions, 1):
            print(f"\n[시도 {i}]")
            for j, q in enumerate(q_list, 1):
                print(f"  {j}. {q}")

        # 완전히 동일한지 확인
        if all_questions[0] == all_questions[1] == (all_questions[2] if len(all_questions) > 2 else all_questions[0]):
            print("\n[OK] 모든 질문이 완전히 동일함!")
        else:
            print("\n[DIFF] 질문 내용이 다름 (일부 또는 전체)")

    # should_continue 비교
    should_continue_vals = [
        r.get("should_continue") for r in results if "should_continue" in r
    ]
    if should_continue_vals:
        print(f"\nshould_continue: {should_continue_vals}")
        if len(set(should_continue_vals)) == 1:
            print("[OK] should_continue 일관됨")
        else:
            print("[DIFF] should_continue가 다름!")

    # 결과를 파일로 저장
    output_path = os.path.join(ROOT, "checklist_consistency_test.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "situation": situation,
                "issue": issue,
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n전체 결과 저장됨: {output_path}")


if __name__ == "__main__":
    main()
