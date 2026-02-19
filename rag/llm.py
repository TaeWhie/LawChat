# GPT-5-nano 호출 및 JSON 파싱
import json
import re
import sys
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import CHAT_MODEL, OPENAI_API_KEY

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
        # gpt-5-nano는 max_completion_tokens 사용, 다른 모델은 max_tokens
        if "gpt-5" in model or "nano" in model.lower():
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
    try:
        r = client.chat.completions.create(**kwargs)
        if not r.choices:
            print("[chat] API 응답에 choices가 없음", file=sys.stderr)
            return ""
        choice = r.choices[0]
        content = choice.message.content
        finish_reason = choice.finish_reason
        
        # 디버깅: 전체 응답 정보 출력
        print(f"[chat] API 응답 - finish_reason: {finish_reason}, content 타입: {type(content)}, content is None: {content is None}", file=sys.stderr)
        print(f"[chat] 전체 응답 객체: model={r.model}, id={r.id}, usage={r.usage if hasattr(r, 'usage') else 'N/A'}", file=sys.stderr)
        if hasattr(choice, 'delta') and choice.delta:
            print(f"[chat] delta 존재: {choice.delta}", file=sys.stderr)
        # 혹시 다른 필드에 content가 있는지 확인
        if not content and hasattr(choice, '__dict__'):
            print(f"[chat] choice.__dict__: {choice.__dict__}", file=sys.stderr)
        
        if content is None:
            # content가 None인 경우, 다른 필드 확인
            print(f"[chat] content가 None. choice 객체: {dir(choice)}, message 객체: {dir(choice.message) if hasattr(choice, 'message') else 'N/A'}", file=sys.stderr)
            # 혹시 delta에 있는지 확인
            if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                content = choice.delta.content
                print(f"[chat] delta에서 content 발견: {content[:100] if content else 'None'}", file=sys.stderr)
            return ""
        
        original_len = len(content) if content else 0
        original_content_repr = repr(content[:500]) if content else "''"
        content = content.strip()
        if not content:
            print(f"[chat] API 응답이 비어있음. finish_reason: {finish_reason}, 원본 길이: {original_len}, 원본 (repr): {original_content_repr}", file=sys.stderr)
            # finish_reason이 length인데 content가 비어있으면 max_completion_tokens가 너무 작을 수 있음
            if finish_reason == "length" and max_tokens is not None:
                print(f"[chat] 경고: finish_reason=length인데 content가 비어있음. max_completion_tokens({max_tokens})가 너무 작거나 시스템 프롬프트가 너무 클 수 있음", file=sys.stderr)
                # 빈 문자열이라도 반환 (혹시 공백만 있을 수 있음)
                return choice.message.content or ""
        elif finish_reason == "length":
            print(f"[chat] 응답이 max_completion_tokens({max_tokens}) 제한으로 잘림. 응답 길이: {len(content)}자", file=sys.stderr)
        return content
    except Exception as e:
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
        print("[chat_json] LLM 응답이 비어있음", file=sys.stderr)
        return None
    parsed = extract_json(raw)
    if parsed is None:
        print(f"[chat_json] JSON 파싱 실패. 원본 응답 (처음 1000자):\n{raw[:1000]}", file=sys.stderr)
        # 잘린 응답일 경우 마지막 부분에서 JSON 시도
        if raw.strip().endswith("]"):
            try:
                # 마지막 ] 앞에서 [ 찾기
                last_bracket = raw.rfind("[")
                if last_bracket >= 0:
                    partial_json = raw[last_bracket:] + "]"
                    parsed = json.loads(partial_json)
                    print(f"[chat_json] 잘린 응답에서 부분 JSON 파싱 성공", file=sys.stderr)
            except:
                pass
    return parsed
