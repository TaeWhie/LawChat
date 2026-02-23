# GPT-5-nano 호출 및 JSON 파싱
import json
import os
import re
import sys
from typing import Any, Dict, Generator, List, Optional

from openai import OpenAI

from config import CHAT_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL

# 프로덕션에서 stderr 노이즈 방지. LAW_DEBUG=1 일 때만 상세 출력
_DEBUG = os.getenv("LAW_DEBUG", "0") == "1"

# OpenAI 클라이언트 전역 재사용 (연결 재사용으로 속도 향상)
# OPENAI_BASE_URL이 설정되면 해당 프록시 엔드포인트 사용 (예: Genspark AI proxy)
_chat_client = None
def _get_chat_client() -> OpenAI:
    global _chat_client
    if _chat_client is None:
        kwargs: dict = {"api_key": OPENAI_API_KEY}
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL
        _chat_client = OpenAI(**kwargs)
    return _chat_client


def chat(
    system: str,
    user: str,
    model: str = CHAT_MODEL,
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
) -> str:
    """
    단일 대화 턴. 응답 텍스트 반환. (gpt-5-nano는 temperature=1만 지원)
    max_tokens: 생성 토큰 수 제한 (None이면 모델 기본값 사용).
    reasoning_effort: 'low'|'medium'|'high'|None. reasoning 모델에서 None이면 'medium'(기본).
                      'low'로 설정 시 reasoning 토큰 대폭 감소 → 응답 속도 3~6배 향상.
    """
    client = _get_chat_client()
    is_reasoning = "gpt-5" in model or "nano" in model.lower()
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    # reasoning_effort 적용 (reasoning 모델 전용)
    if is_reasoning and reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort

    if max_tokens is not None:
        if is_reasoning:
            # reasoning 모델: reasoning_effort=low 이면 reasoning 토큰이 적어 2000으로도 충분
            # effort=None|medium|high 이면 reasoning 토큰이 많아 최소 3000 이상 필요
            min_required = 2000 if reasoning_effort == "low" else 3000
            if max_tokens < min_required:
                if _DEBUG:
                    print(f"[chat] reasoning 모델, max_tokens({max_tokens}) < {min_required} → {min_required}으로 보정", file=sys.stderr)
                max_tokens = min_required
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
    elif is_reasoning and reasoning_effort == "low":
        # effort=low일 때 상한 없으면 불필요하게 긴 응답 방지
        kwargs["max_completion_tokens"] = 4000

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


def chat_with_metadata(
    system: str,
    user: str,
    model: str = CHAT_MODEL,
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    """
    단일 대화 턴. 단순 텍스트가 아닌 메타데이터(프롬프트 전문, raw_response, 모델명 등)를 포함한 딕셔너리 반환.
    """
    content = chat(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort
    )
    return {
        "content": content,
        "system_prompt": system,
        "user_prompt": user,
        "model": model,
        "reasoning_effort": reasoning_effort
    }

def chat_json(
    system: str,
    user: str,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
    return_metadata: bool = False,
) -> Any:
    """
    채팅 후 응답에서 JSON 파싱. 
    return_metadata=True 이면 (parsed_json, debug_info_dict) 형태의 튜플 반환.
    """
    raw = chat(system, user, max_tokens=max_tokens, reasoning_effort=reasoning_effort)
    if not raw:
        if _DEBUG:
            print("[chat_json] LLM 응답이 비어있음", file=sys.stderr)
        return (None, {}) if return_metadata else None
        
    parsed = extract_json(raw)
    if parsed is None:
        if _DEBUG:
            print(f"[chat_json] JSON 파싱 실패. 원본 응답 (처음 1000자):\n{raw[:1000]}", file=sys.stderr)
        if raw.strip().endswith("]"):
            try:
                last_bracket = raw.rfind("[")
                if last_bracket >= 0:
                    partial_json = raw[last_bracket:] + "]"
                    parsed = json.loads(partial_json)
            except Exception:
                pass
                
    if return_metadata:
        debug_info = {
            "system_prompt": system,
            "user_prompt": user,
            "raw_response": raw,
            "parsed_success": parsed is not None
        }
        return (parsed, debug_info)
    return parsed


def chat_stream(
    system: str,
    user: str,
    model: str = CHAT_MODEL,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
) -> Generator[str, None, None]:
    """
    스트리밍 응답을 청크(str) 제너레이터로 반환.
    Streamlit에서 st.write_stream()과 함께 사용.
    gpt-5-nano reasoning 모델도 지원 (streaming=True).
    reasoning_effort='low' 설정 시 첫 청크 도달까지 시간 대폭 단축.
    """
    client = _get_chat_client()
    is_reasoning = "gpt-5" in model or "nano" in model.lower()
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 1.0,
        "stream": True,
    }
    if is_reasoning and reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort

    if max_tokens is not None:
        if is_reasoning:
            min_required = 2000 if reasoning_effort == "low" else 3000
            kwargs["max_completion_tokens"] = max(max_tokens, min_required)
        else:
            kwargs["max_tokens"] = max_tokens

    try:
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content
    except Exception as e:
        if _DEBUG:
            print(f"[chat_stream] 스트리밍 오류: {type(e).__name__}: {e}", file=sys.stderr)
        raise


def chat_json_fast(
    system: str,
    user: str,
    max_tokens: int = 200,
    return_metadata: bool = False,
) -> Any:
    """
    단순 판단(off-topic, checklist_continuation 등) 전용 빠른 JSON 호출.
    reasoning_effort='low'를 지원하는 모델에서는 reasoning 오버헤드 최소화.
    지원 안 하면 일반 chat_json으로 폴백.
    return_metadata=True 이면 (parsed_json, debug_info_dict) 형태의 튜플 반환.
    """
    client = _get_chat_client()
    model = CHAT_MODEL
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 1.0,
    }

    # reasoning 모델용: reasoning_effort='low' 적용 (API 지원 시)
    is_reasoning = "gpt-5" in model or "nano" in model.lower()
    if is_reasoning:
        kwargs["reasoning_effort"] = "low"
        # max_completion_tokens: reasoning budget 제한
        kwargs["max_completion_tokens"] = max(max_tokens, 1000)
    else:
        kwargs["max_tokens"] = max_tokens

    try:
        r = client.chat.completions.create(**kwargs)
        if not r.choices:
            return (None, {}) if return_metadata else None
        
        content = (r.choices[0].message.content or "").strip()
        if not content:
            return (None, {}) if return_metadata else None
            
        parsed = extract_json(content)
        if _DEBUG and parsed is None:
            print(f"[chat_json_fast] JSON 파싱 실패: {content[:300]}", file=sys.stderr)
            
        if return_metadata:
            debug_info = {
                "system_prompt": system,
                "user_prompt": user,
                "raw_response": content,
                "parsed_success": parsed is not None
            }
            return (parsed, debug_info)
            
        return parsed
    except Exception as e:
        # reasoning_effort 미지원 API → 일반 chat_json으로 폴백
        if _DEBUG:
            print(f"[chat_json_fast] 폴백 (reasoning_effort 미지원): {e}", file=sys.stderr)
        return chat_json(system, user, max_tokens=max_tokens, return_metadata=return_metadata)
