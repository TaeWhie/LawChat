import json
import os
import requests

BASE_URL = "https://law-chat-api.onrender.com"
TIMEOUT = 90

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")
OUT_PATH_SINGLE = os.path.join(ROOT, "checklist_batch_result.json")
OUT_PATH_MULTI = os.path.join(ROOT, "checklist_batch_multi_result.json")


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


def run_scenario(
    session: requests.Session,
    api_key: str,
    situation: str,
    top_k: int = 22,
    max_issues: int = 5,
    max_rounds: int = 3,
    default_answer: str = "모르겠음",
):
    result = {
        "situation": situation,
        "top_k": top_k,
        "max_issues": max_issues,
        "max_rounds": max_rounds,
        "classify": None,
        "checklists": [],
    }

    body_classify = {
        "situation": situation,
        "top_k": top_k,
        "openai_api_key": api_key,
    }
    code_c, data_c = api_post(session, "/api/v1/chat/classify", body_classify)
    result["classify"] = {"status_code": code_c, "data": data_c}

    if code_c != 200:
        return result

    issues = (data_c.get("issues") or [])[:max_issues]

    for issue in issues:
        issue_entry = {
            "issue": issue,
            "rounds": [],
        }
        all_qa = []
        previous_rag = []
        for r in range(1, max_rounds + 1):
            body_cl = {
                "issue": issue,
                "situation": situation,
                "all_qa": all_qa,
                "round": r,
                "previous_rag_results": previous_rag,
                "openai_api_key": api_key,
            }
            code_cl, data_cl = api_post(session, "/api/v1/chat/checklist", body_cl)
            round_entry = {
                "round": r,
                "status_code": code_cl,
                "data": data_cl,
            }
            issue_entry["rounds"].append(round_entry)

            if code_cl != 200:
                break

            checklist_items = data_cl.get("checklist") or []
            questions = [
                (item.get("question") or item.get("item") or str(item))
                for item in checklist_items
            ]
            should_continue = data_cl.get("should_continue")

            all_qa = all_qa + [
                {"question": q, "answer": default_answer} for q in questions
            ]
            previous_rag = data_cl.get("rag_results") or []

            if not questions:
                break
            if should_continue is not True:
                break

        result["checklists"].append(issue_entry)

    return result


def main():
    api_key = load_openai_api_key(ENV_PATH)
    session = requests.Session()

    # 여러 다른 상황에 대한 배치 실행
    scenarios = [
        {
            "id": "unpaid_wage",
            "situation": "월급을 두 달째 못 받았어요.",
        },
        {
            "id": "severance_pay",
            "situation": "2년 근무 후 퇴사했는데 퇴직금을 안 준다고 합니다.",
        },
        {
            "id": "unfair_dismissal",
            "situation": "사전 예고도 없이 갑자기 해고 통보를 받았습니다.",
        },
        {
            "id": "workplace_bullying",
            "situation": "상사가 회식 때마다 사람들 앞에서 반복적으로 모욕을 줍니다.",
        },
        {
            "id": "working_hours",
            "situation": "주당 60시간 넘게 일하는데 추가 수당을 못 받고 있습니다.",
        },
    ]

    multi_result = []

    for sc in scenarios:
        sc_result = run_scenario(
            session=session,
            api_key=api_key,
            situation=sc["situation"],
            top_k=22,
            max_issues=5,
            max_rounds=3,
            default_answer="모르겠음",
        )
        sc_wrapped = {
            "id": sc.get("id"),
            "situation": sc["situation"],
            "result": sc_result,
        }
        multi_result.append(sc_wrapped)

    # 첫 번째 시나리오는 기존 단일 결과 파일에도 저장 (호환용)
    if multi_result:
        with open(OUT_PATH_SINGLE, "w", encoding="utf-8") as f:
            json.dump(multi_result[0]["result"], f, ensure_ascii=False, indent=2)

    with open(OUT_PATH_MULTI, "w", encoding="utf-8") as f:
        json.dump(multi_result, f, ensure_ascii=False, indent=2)

    print(f"Multi-scenario result saved to {OUT_PATH_MULTI}")


if __name__ == "__main__":
    main()
