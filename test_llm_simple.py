# -*- coding: utf-8 -*-
"""간단한 LLM 호출 테스트"""

import os
os.environ["LAW_DEBUG"] = "1"

from rag.llm import chat
from rag.question_classifier import system_knowledge_qa, user_knowledge_qa

print("="*60)
print("간단한 LLM 호출 테스트")
print("="*60)

# 간단한 테스트
system = "You are a helpful assistant. Answer in Korean."
user = "안녕하세요"

print(f"\n시스템: {system}")
print(f"사용자: {user}")
print("\nLLM 호출 중...")

try:
    answer = chat(system, user, max_tokens=50)
    print(f"\n답변: {repr(answer)}")
    print(f"답변 길이: {len(answer) if answer else 0}자")
    
    if not answer or len(answer.strip()) == 0:
        print("\n❌ 답변이 비어있습니다!")
        print("가능한 원인:")
        print("1. API 키가 설정되지 않았거나 잘못됨")
        print("2. 모델이 응답을 생성하지 못함")
        print("3. 네트워크 오류")
    else:
        print("\n✅ LLM 호출 성공!")
except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()

# 지식 질문 프롬프트 테스트
print("\n" + "="*60)
print("지식 질문 프롬프트 테스트")
print("="*60)

system_prompt = system_knowledge_qa()
user_prompt = user_knowledge_qa("통상임금과 평균임금의 차이", "테스트 컨텍스트")

print(f"\n시스템 프롬프트 길이: {len(system_prompt)}자")
print(f"사용자 프롬프트 길이: {len(user_prompt)}자")
print("\nLLM 호출 중...")

try:
    answer = chat(system_prompt, user_prompt, max_tokens=200)
    print(f"\n답변: {repr(answer)}")
    print(f"답변 길이: {len(answer) if answer else 0}자")
    
    if answer and len(answer.strip()) > 0:
        print(f"\n답변 내용:\n{answer}")
        print("\n✅ 지식 질문 프롬프트 테스트 성공!")
    else:
        print("\n❌ 답변이 비어있습니다!")
except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()