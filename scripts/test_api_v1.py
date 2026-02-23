import httpx
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_api_flow():
    with httpx.Client(timeout=60.0) as client:
        # 1. Route Test
        print("\n--- Testing Route ---")
        res = client.post(f"{BASE_URL}/api/v1/chat/route", json={"text": "퇴직금을 못 받았어요"})
        print(f"Route Response: {res.json()}")
        
        # 2. Classify Test
        print("\n--- Testing Classify ---")
        situation = "2년 동안 카페에서 일했는데 퇴직금을 못 받고 해고당했어요."
        res = client.post(f"{BASE_URL}/api/v1/chat/classify", json={"situation": situation})
        classify_data = res.json()
        issues = classify_data.get("issues", [])
        print(f"Detected Issues: {issues}")
        
        if not issues:
            print("No issues detected. Stopping test.")
            return

        selected_issue = issues[0]
        
        # 3. Checklist Test
        print(f"\n--- Testing Checklist for: {selected_issue} ---")
        res = client.post(f"{BASE_URL}/api/v1/chat/checklist", json={
            "issue": selected_issue,
            "situation": situation
        })
        checklist_data = res.json()
        checklist = checklist_data.get("checklist", [])
        print(f"Checklist items: {len(checklist)}")
        
        # Simulate answers
        all_qa = []
        for item in checklist[:2]: # Test with first 2 items
            q = item.get("question") or item.get("item")
            all_qa.append({"question": q, "answer": "네"})
            
        # 4. Conclusion Test (Non-streaming)
        print("\n--- Testing Conclusion ---")
        res = client.post(f"{BASE_URL}/api/v1/chat/conclusion", json={
            "issue": selected_issue,
            "all_qa": all_qa,
            "stream": False
        })
        conclusion_data = res.json()
        print(f"Conclusion length: {len(conclusion_data.get('conclusion', ''))}")
        print(f"Related Articles: {conclusion_data.get('related_articles', [])}")
        print(f"Related Questions: {len(conclusion_data.get('related_questions', []))}")

        # 5. Law Browsing Test
        print("\n--- Testing Law List ---")
        res = client.get(f"{BASE_URL}/api/v1/laws/list")
        laws = res.json()
        print(f"Laws found: {len(laws)}")

        if laws and isinstance(laws, list):
            law_id = laws[0].get("id") if isinstance(laws[0], dict) else None
            source = laws[0].get("source") if isinstance(laws[0], dict) else None
            print(f"\n--- Testing Law Chapters for: {law_id} ---")
            res = client.get(f"{BASE_URL}/api/v1/laws/chapters", params={"law_id": law_id, "source": source})
            chapters = res.json()
            print(f"Chapters found: {len(chapters)}")

        # 6. Specialized QA Tests
        print("\n--- Testing Knowledge QA ---")
        res = client.post(f"{BASE_URL}/api/v1/chat/qa/knowledge", json={"question": "퇴직금 분할 약정이 유효한가요?"})
        data = res.json()
        ans = data.get('answer')
        print(f"Knowledge Answer: {str(ans)[:100]}...")

        print("\n--- Testing Calculation QA ---")
        res = client.post(f"{BASE_URL}/api/v1/chat/qa/calculation", json={"question": "평균임금 20만원, 근속 2년인 경우 퇴직금은 얼마인가요?"})
        data = res.json()
        ans = data.get('answer')
        print(f"Calculation Answer: {str(ans)[:100]}...")

        print("\n--- Testing Documents QA ---")
        res = client.post(f"{BASE_URL}/api/v1/chat/qa/documents", json={"question": "해고예보 통보서 서식이 있나요?"})
        data = res.json()
        ans = data.get('answer')
        print(f"Documents Answer: {str(ans)[:100]}...")

if __name__ == "__main__":
    # Note: Make sure main_api.py is running before executing this
    try:
        test_api_flow()
    except Exception as e:
        import traceback
        print(f"Error during test: {e}")
        traceback.print_exc()
