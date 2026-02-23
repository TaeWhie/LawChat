import json
from rag.pipeline import step1_issue_classification
from rag.store import build_vector_store

def test_serialization():
    col, _ = build_vector_store()
    situation = "퇴직금을 못 받았어요"
    issues, articles_by_issue, _, _ = step1_issue_classification(situation, collection=col)
    
    # 1. Try to serialize the raw dict
    try:
        json.dumps(articles_by_issue)
        print("Raw articles_by_issue is JSON serializable")
    except Exception as e:
        print(f"Raw articles_by_issue fails serialization: {e}")

    # 2. Try the simplified logic used in main_api.py
    safe_articles = {}
    for issue, articles in articles_by_issue.items():
        safe_articles[str(issue)] = []
        for a in articles:
            # ONLY include known safe strings
            safe_articles[str(issue)].append({
                "article": str(a.get("article", "")),
                "title": str(a.get("title", ""))
            })
    
    try:
        json_str = json.dumps(safe_articles)
        print("Simplified articles are JSON serializable")
        # print(json_str[:500])
    except Exception as e:
        print(f"Simplified articles still fail serialization: {e}")

if __name__ == "__main__":
    test_serialization()
