# GPT-5-nano 호출 및 JSON 파싱
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import CHAT_MODEL, OPENAI_API_KEY

# 프로덕션에서 stderr 노이즈 방지. LAW_DEBUG=1 일 때만 상세 출력
_DEBUG = os.getenv("LAW_DEBUG", "0") == "1"

# OpenAI 클라이언트 전역 재사용 (연결 재사용으로 속도 향상)
_chat_client = None
def _get_chat_client() -> OpenAI:
    global _chat_client
    if _chat_client is None:
        _chat_client = OpenAI(api_key=OPENAI_API_KEY)
    return _chat_client


def chat(
    system: str,
    user: str,
    model: str = CHAT_MODEL,
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
) -> str:
    """
    단일 대화 턴. 응답 텍스트 반환. (gpt-5-nano는 temperature=1만 지원)
    max_tokens: 생성 토큰 수 제한 (None이면 모델 기본값 사용). 제한 시 생성 시간 단축.
    """
    client = _get_chat_client()
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if max_tokens is not None:
        # gpt-5-nano는 reasoning 모델 → reasoning_tokens 사용하므로 실제 출력을 위해 더 큰 값 필요
        # reasoning 모델은 max_completion_tokens 사용하되, reasoning 토큰을 제외한 실제 출력을 위해 충분히 큰 값 필요
        if "gpt-5" in model or "nano" in model.lower():
            # reasoning 모델: reasoning_tokens가 대부분이므로 실제 출력을 위해 최소 1000 이상 필요
            # max_tokens가 너무 작으면 reasoning만 하고 출력 없음
            if max_tokens < 1000:
                # 작은 값이면 None으로 설정하여 모델이 충분히 출력하도록 함
                if _DEBUG:
                    print(f"[chat] reasoning 모델 감지, max_tokens({max_tokens})가 너무 작아 None으로 설정", file=sys.stderr)
                max_tokens = None
            if max_tokens is not None:
                kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
    try:
        r = client.chat.completions.create(**kwargs)
        if not r.choices:
            if _DEBUG:
                print("[chat] API 응답에 choices가 없음", file=sys.stderr)
            return ""
        choice = r.choices[0]
        content = choice.message.content
        finish_reason = choice.finish_reason

        if _DEBUG:
            print(f"[chat] API 응답 - finish_reason: {finish_reason}, content 타입: {type(content)}, content is None: {content is None}", file=sys.stderr)
            print(f"[chat] 전체 응답 객체: model={r.model}, id={r.id}, usage={r.usage if hasattr(r, 'usage') else 'N/A'}", file=sys.stderr)
            if hasattr(choice, 'delta') and choice.delta:
                print(f"[chat] delta 존재: {choice.delta}", file=sys.stderr)
            if not content and hasattr(choice, '__dict__'):
                print(f"[chat] choice.__dict__: {choice.__dict__}", file=sys.stderr)

        if content is None:
            if _DEBUG:
                print(f"[chat] content가 None. choice 객체: {dir(choice)}, message 객체: {dir(choice.message) if hasattr(choice, 'message') else 'N/A'}", file=sys.stderr)
            if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                content = choice.delta.content
                if _DEBUG and content:
                    print(f"[chat] delta에서 content 발견: {content[:100]}", file=sys.stderr)
            return ""

        original_len = len(content) if content else 0
        original_content_repr = repr(content[:500]) if content else "''"
        content = content.strip()
        if not content:
            if _DEBUG:
                print(f"[chat] API 응답이 비어있음. finish_reason: {finish_reason}, 원본 길이: {original_len}, 원본 (repr): {original_content_repr}", file=sys.stderr)
                if finish_reason == "length" and max_tokens is not None:
                    print(f"[chat] 경고: finish_reason=length인데 content가 비어있음. max_completion_tokens({max_tokens})", file=sys.stderr)
            return choice.message.content or ""
        if _DEBUG and finish_reason == "length":
            print(f"[chat] 응답이 max_completion_tokens({max_tokens}) 제한으로 잘림. 응답 길이: {len(content)}자", file=sys.stderr)
        return content
    except Exception as e:
        if _DEBUG:
            print(f"[chat] API 호출 오류: {type(e).__name__}: {str(e)}", file=sys.stderr)
        raise


def extract_json(text: str) -> Optional[Any]:
    """응답 텍스트에서 JSON 블록 추출."""
    text = text.strip()
    # ```json ... ``` 제거
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    # [... ] 또는 {... } 찾기
    for start, end in [("[", "]"), ("{", "}")]:
        i = text.find(start)
        if i == -1:
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == start:
                depth += 1
            elif text[j] == end:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[i : j + 1])
                    except json.JSONDecodeError:
                        pass
                    break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def chat_json(system: str, user: str, max_tokens: Optional[int] = None) -> Optional[Any]:
    """채팅 후 응답에서 JSON 파싱. max_tokens로 생성 시간 단축 가능."""
    raw = chat(system, user, max_tokens=max_tokens)
    if not raw:
        if _DEBUG:
            print("[chat_json] LLM 응답이 비어있음", file=sys.stderr)
        return None
    parsed = extract_json(raw)
    if parsed is None:
        if _DEBUG:
            print(f"[chat_json] JSON 파싱 실패. 원본 응답 (처음 1000자):\n{raw[:1000]}", file=sys.stderr)
        # 잘린 응답일 경우 마지막 부분에서 JSON 시도
        if raw.strip().endswith("]"):
            try:
                # 마지막 ] 앞에서 [ 찾기
                last_bracket = raw.rfind("[")
                if last_bracket >= 0:
                    partial_json = raw[last_bracket:] + "]"
                    parsed = json.loads(partial_json)
                    if _DEBUG:
                        print(f"[chat_json] 잘린 응답에서 부분 JSON 파싱 성공", file=sys.stderr)
            except Exception:
                pass
    return parsed
