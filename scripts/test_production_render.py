import httpx
import json
import time
import os
from dotenv import load_dotenv

# 로컬 .env 로드 (테스트용 키)
load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
LAW_KEY = os.getenv("LAW_API_OC")

print(f"DEBUG: Local OpenAI Key exists: {bool(OPENAI_KEY)}")
print(f"DEBUG: Local Law Key exists: {bool(LAW_KEY)}")


# 운영 서버 주소
BASE_URL = "https://law-chat-api.onrender.com"
# BASE_URL = "http://127.0.0.1:8001"

def test_production_api():
    print(f"🚀 LawChat 운영 서버 테스트 시작: {BASE_URL}")
    print("="*60)
    
    with httpx.Client(timeout=60.0) as client:
        # 0. Health Check (Version 확인)
        print("\n[테스트 0] 서버 버전 확인")
        try:
            res = client.get(f"{BASE_URL}/api/v1/health")
            if res.status_code == 200:
                data = res.json()
                print(f"✅ 서버 버전: {data.get('version')}")
                if data.get('version') != "1.0.4-fixed-propagation":
                    print("⚠️ 서버가 아직 예전 버전입니다. 잠시 후 다시 시도하세요.")
                    # return # 일단 계속 진행
            else:
                print(f"❌ 헬스체크 실패: {res.status_code}")
        except Exception as e:
            print(f"❌ 서버 접속 실패: {e}")
            return

        # 1. 문서(Docs) 확인
        print("\n[테스트 1] 서버 생존 확인 (Docs)")
        try:
            res = client.get(f"{BASE_URL}/docs")
            if res.status_code == 200:
                print("✅ 서버가 온라인 상태이며 문서 페이지가 정상입니다.")
            else:
                print(f"❌ 서버 응답 이상: {res.status_code}")
        except Exception as e:
            print(f"❌ 서버 접속 실패: {e}")
            return

        # 2. 이슈 분류 테스트 (동적 API 키 주입)
        print("\n[테스트 2] 이슈 분류 (동적 API 키 주입 테스트)")
        payload = {
            "situation": "임금체불 때문에 퇴직을 고민 중입니다.",
            "top_k": 3,
            "openai_api_key": OPENAI_KEY,
            "law_api_key": LAW_KEY
        }
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/classify", json=payload)
            if res.status_code == 200:
                data = res.json()
                print(f"✅ 분류 성공! 탐지된 이슈: {data.get('issues', [])}")
            else:
                print(f"❌ 분류 실패: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ API 호출 오류: {e}")

        # 3. 지식 QA 테스트 (동적 API 키 주입)
        print("\n[테스트 3] 법률 지식 QA (RAG 기능 테스트)")
        payload = {
            "question": "퇴직금은 언제까지 지급해야 하나요?",
            "top_k": 3,
            "openai_api_key": OPENAI_KEY,
            "law_api_key": LAW_KEY
        }
        try:
            res = client.post(f"{BASE_URL}/api/v1/chat/qa/knowledge", json=payload)
            if res.status_code == 200:
                data = res.json()
                answer = data.get("answer", "")
                print(f"✅ QA 성공! 답변 요약: {answer[:100]}...")
            else:
                print(f"❌ QA 실패: {res.status_code}")
        except Exception as e:
            print(f"❌ API 호출 오류: {e}")

    print("\n" + "="*60)
    print("🎉 모든 기본 기능 테스트가 완료되었습니다.")

if __name__ == "__main__":
    test_production_api()
