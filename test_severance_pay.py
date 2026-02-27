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
    situation = "퇴직금을 못받았어요"
    
    print("=" * 60)
    print("퇴직금 체크리스트 테스트")
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
    
    print("\n" + "=" * 60)
    print("생성된 체크리스트 질문:")
    print("=" * 60)
    for i, item in enumerate(checklist, 1):
        question = item.get("question") or item.get("item") or str(item)
        item_title = item.get("item", "")
        print(f"\n{i}. [{item_title}]")
        print(f"   Q: {question}")
    
    # 중복 체크
    print("\n" + "=" * 60)
    print("중복 체크:")
    print("=" * 60)
    questions = [item.get("question") or item.get("item") or "" for item in checklist]
    seen = set()
    duplicates = []
    for i, q in enumerate(questions, 1):
        q_normalized = q.lower().strip()
        if q_normalized in seen:
            duplicates.append(i)
        seen.add(q_normalized)
    
    if duplicates:
        print(f"[WARNING] 중복된 질문 발견: {duplicates}번")
    else:
        print("[OK] 중복된 질문 없음")
    
    # 유사도 체크 (간단히)
    print("\n유사 질문 분석:")
    from rag.pipeline import _normalize_question_for_similarity
    word_sets = [_normalize_question_for_similarity(q) for q in questions]
    similar_pairs = []
    for i in range(len(word_sets)):
        for j in range(i + 1, len(word_sets)):
            overlap = len(word_sets[i] & word_sets[j])
            if overlap >= 2:
                similar_pairs.append((i + 1, j + 1, overlap))
    
    if similar_pairs:
        print(f"[WARNING] 유사한 질문 쌍 발견:")
        for i, j, overlap in similar_pairs:
            print(f"  - {i}번과 {j}번 질문: {overlap}개 키워드 겹침")
            print(f"    {i}번: {questions[i-1]}")
            print(f"    {j}번: {questions[j-1]}")
    else:
        print("[OK] 유사한 질문 없음")
    
    # 결과 저장
    output_path = os.path.join(ROOT, "severance_pay_test_result.json")
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
