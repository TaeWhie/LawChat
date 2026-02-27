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

    # 테스트 상황
    situation = "주당 60시간 넘게 일하는데 추가 수당을 못 받고 있습니다."
    
    print("=" * 60)
    print("체크리스트 테스트")
    print("=" * 60)
    print(f"\n상황: {situation}\n")

    # 1단계: 이슈 분류
    print("[1단계] 이슈 분류 중...")
    body_classify = {
        "situation": situation,
        "top_k": 22,
        "openai_api_key": api_key,
    }
    code_c, data_c = api_post(session, "/api/v1/chat/classify", body_classify)
    
    if code_c != 200:
        print(f"[ERROR] 이슈 분류 실패: {code_c}")
        print(json.dumps(data_c, ensure_ascii=False, indent=2))
        return
    
    issues = data_c.get("issues", [])
    articles_by_issue = data_c.get("articles_by_issue", {})
    
    print(f"[OK] 이슈 분류 완료: {issues}")
    print(f"\n이슈별 조문 수:")
    for issue, articles in articles_by_issue.items():
        print(f"  - {issue}: {len(articles)}개")
        # 조문 구조 확인
        if articles:
            first_article = articles[0]
            print(f"    첫 번째 조문 구조: {list(first_article.keys())}")
            if "text" in first_article:
                print(f"    [OK] 완전한 RAG 구조 (text 필드 있음)")
            elif "article" in first_article and "title" in first_article:
                print(f"    [WARNING] 간단한 구조 (article, title만)")
    
    if not issues:
        print("[ERROR] 이슈가 없습니다.")
        return
    
    # 2단계: 첫 번째 이슈로 체크리스트 생성
    issue = issues[0]
    print(f"\n[2단계] 체크리스트 생성 중 (이슈: {issue})...")
    
    # 이슈 분류에서 받은 articles_by_issue를 previous_rag_results로 전달
    previous_rag = articles_by_issue.get(issue, [])
    
    body_cl = {
        "issue": issue,
        "situation": situation,
        "all_qa": [],
        "round": 1,
        "previous_rag_results": previous_rag,
        "openai_api_key": api_key,
    }
    
    code_cl, data_cl = api_post(session, "/api/v1/chat/checklist", body_cl)
    
    if code_cl != 200:
        print(f"[ERROR] 체크리스트 생성 실패: {code_cl}")
        print(json.dumps(data_cl, ensure_ascii=False, indent=2))
        return
    
    checklist = data_cl.get("checklist", [])
    rag_results = data_cl.get("rag_results", [])
    should_continue = data_cl.get("should_continue")
    
    print(f"[OK] 체크리스트 생성 완료")
    print(f"\n생성된 질문 수: {len(checklist)}개")
    print(f"RAG 결과 수: {len(rag_results)}개")
    print(f"should_continue: {should_continue}")
    
    print("\n생성된 질문:")
    for i, item in enumerate(checklist, 1):
        question = item.get("question") or item.get("item") or str(item)
        print(f"  {i}. {question}")
    
    print("\nRAG 결과 구조 확인:")
    if rag_results:
        for i, r in enumerate(rag_results[:3], 1):  # 처음 3개만 확인
            print(f"\n  [{i}] 조문: {r.get('article', 'N/A')}")
            print(f"      구조: {list(r.keys())}")
            if "text" in r:
                print(f"      [OK] 완전한 RAG 구조")
            elif "article" in r and "title" in r and len(r) == 2:
                print(f"      [WARNING] 간단한 구조 (정규화 필요)")
    
    # 결과 저장
    output_path = os.path.join(ROOT, "checklist_test_result.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "situation": situation,
                "classify": {"status_code": code_c, "data": data_c},
                "checklist": {"status_code": code_cl, "data": data_cl},
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n결과 저장됨: {output_path}")


if __name__ == "__main__":
    main()
