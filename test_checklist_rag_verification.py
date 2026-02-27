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

    # 테스트 상황
    situation = "주당 60시간 넘게 일하는데 추가 수당을 못 받고 있습니다."
    
    print(f"테스트 상황: {situation}")
    print("\n1단계: 이슈 분류 중...")
    
    # 1단계: 이슈 분류
    body_classify = {
        "situation": situation,
        "top_k": 22,
        "openai_api_key": api_key,
    }
    code_c, data_c = api_post(session, "/api/v1/chat/classify", body_classify)
    
    if code_c != 200:
        print(f"이슈 분류 실패: {code_c}")
        return
    
    issues = data_c.get("issues", [])
    print(f"분류된 이슈: {issues}")
    
    if not issues:
        print("이슈가 없습니다.")
        return
    
    issue = issues[0]
    print(f"\n2단계: 체크리스트 생성 중 (이슈: {issue})...")
    
    # 2단계: 체크리스트 생성
    body_checklist = {
        "issue": issue,
        "situation": situation,
        "all_qa": [],
        "round": 1,
        "previous_rag_results": [],
        "openai_api_key": api_key,
    }
    code_cl, data_cl = api_post(session, "/api/v1/chat/checklist", body_checklist)
    
    if code_cl != 200:
        print(f"체크리스트 생성 실패: {code_cl}")
        return
    
    checklist = data_cl.get("checklist", [])
    rag_results = data_cl.get("rag_results", [])
    related_provisions = data_cl.get("related_provisions_summary", [])
    
    print(f"\n생성된 체크리스트 질문: {len(checklist)}개")
    for i, item in enumerate(checklist, 1):
        q = item.get("question") or item.get("item") or str(item)
        print(f"  {i}. {q}")
    
    print(f"\nRAG로 검색된 조문: {len(rag_results)}개")
    if rag_results:
        print("\n사용된 조문 목록:")
        seen_articles = set()
        for r in rag_results[:10]:  # 상위 10개만 표시
            source = r.get("source", "")
            article = r.get("article", "")
            key = f"{source} {article}"
            if key not in seen_articles:
                seen_articles.add(key)
                text_preview = (r.get("text", "") or "")[:100].replace("\n", " ")
                print(f"  - {source} {article}")
                if text_preview:
                    print(f"    {text_preview}...")
    
    if related_provisions:
        print(f"\n관련 조문 요약: {len(related_provisions)}개")
        for i, prov in enumerate(related_provisions[:5], 1):  # 상위 5개만 표시
            print(f"  {i}. {prov[:150]}...")
    
    # 결과 저장
    output_path = os.path.join(ROOT, "checklist_rag_verification.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "situation": situation,
                "issue": issue,
                "checklist": checklist,
                "rag_results_count": len(rag_results),
                "rag_results_sample": rag_results[:5] if rag_results else [],
                "related_provisions_count": len(related_provisions),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n결과 저장됨: {output_path}")


if __name__ == "__main__":
    main()
