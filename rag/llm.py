# GPT-5-nano 호출 및 JSON 파싱
import json
import os
import re
import sys
from typing import Any, Dict, Generator, List, Optional

from openai import OpenAI

from config import CHAT_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL
from rag.context import (
    openai_api_key_ctx,
    openai_base_url_ctx,
    chat_model_ctx,
    temperature_ctx,
    max_tokens_ctx,
    reasoning_effort_ctx,
    top_p_ctx,
)

# 프로덕션에서 stderr 노이즈 방지. LAW_DEBUG=1 일 때만 상세 출력
_DEBUG = os.getenv("LAW_DEBUG", "0") == "1"

# OpenAI 클라이언트 캐시 (API 키별로 구분)
_clients: Dict[str, OpenAI] = {}

def _get_chat_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAI:
    """
    1. 인자로 넘어온 키 (최우선)
    2. 컨텍스트에서 키 가져오기 (차선)
    3. 기본 키 사용 (최후)
    """
    actual_api_key = api_key or openai_api_key_ctx.get() or OPENAI_API_KEY
    actual_base_url = base_url or openai_base_url_ctx.get() or OPENAI_BASE_URL
    if not actual_api_key or (isinstance(actual_api_key, str) and not actual_api_key.strip()):
        raise ValueError(
            "OpenAI API 키가 없습니다. 요청 바디에 openai_api_key를 넣거나, 서버에 OPENAI_API_KEY 환경변수를 설정하세요."
        )
    actual_api_key = actual_api_key.strip() if isinstance(actual_api_key, str) else actual_api_key

    # 캐시 키 생성 (키와 베이스 URL 조합)
    cache_key = f"{actual_api_key}|{actual_base_url}"

    if cache_key not in _clients:
        kwargs: dict = {"api_key": actual_api_key}
        if actual_base_url:
            kwargs["base_url"] = actual_base_url
        _clients[cache_key] = OpenAI(**kwargs)
        
    return _clients[cache_key]


def _resolve_model_params(
    temperature: float = 0.0,
    max_tokens: int = 2000,
    reasoning_effort: Optional[str] = None,
    top_p: Optional[float] = None,
) -> tuple:
    """ContextVar가 설정되어 있으면 우선 사용, 없으면 인자값 반환."""
    t = temperature_ctx.get()
    temp = t if t is not None else temperature
    m = max_tokens_ctx.get()
    tok = m if m is not None else max_tokens
    r = reasoning_effort_ctx.get()
    eff = r if r is not None else reasoning_effort
    p = top_p_ctx.get()
    top_p_val = p if p is not None else top_p
    return temp, tok, eff, top_p_val


def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    reasoning_effort: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> str:
    """기본 채팅 응답. model 미지정 시 chat_model_ctx → CHAT_MODEL 순으로 사용. temperature/max_tokens/reasoning_effort/top_p는 context 우선."""
    actual_model = model or chat_model_ctx.get() or CHAT_MODEL
    temp, tok, eff, top_p_val = _resolve_model_params(temperature, max_tokens, reasoning_effort, None)
    client = _get_chat_client(openai_api_key, openai_base_url)
    m_lower = actual_model.lower()
    is_reasoning = "gpt-5" in m_lower or "nano" in m_lower or m_lower.startswith("o1") or m_lower.startswith("o3")

    kwargs: Dict[str, Any] = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    if not is_reasoning:
        kwargs["temperature"] = temp
        if top_p_val is not None:
            kwargs["top_p"] = top_p_val

    if tok is not None:
        if is_reasoning:
            kwargs["max_completion_tokens"] = tok
        else:
            kwargs["max_tokens"] = tok

    if is_reasoning and eff is not None:
        kwargs["reasoning_effort"] = eff

    try:
        r = client.chat.completions.create(**kwargs)
        if not r.choices:
            return ""
        content = r.choices[0].message.content
        return content.strip() if content else ""
    except Exception as e:
        actual_api_key = openai_api_key or openai_api_key_ctx.get() or OPENAI_API_KEY
        key_info = f"Used Key: {actual_api_key[:7]}...{actual_api_key[-4:]}" if actual_api_key else "None"
        new_msg = f"{str(e)} | [{key_info}]"
        if _DEBUG:
            print(f"[chat] API 호출 오류: {new_msg}", file=sys.stderr)
        raise Exception(new_msg)


def extract_json(text: str) -> Optional[Any]:
    """응답 텍스트에서 JSON 블록 추출."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
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


def chat_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    reasoning_effort: Optional[str] = None,
    return_metadata: bool = False,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Any:
    """JSON 모드 응답. model 미지정 시 chat_model_ctx → CHAT_MODEL 순으로 사용."""
    actual_model = model or chat_model_ctx.get() or CHAT_MODEL
    raw = chat(
        system_prompt, 
        user_prompt, 
        model=actual_model, 
        temperature=temperature, 
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url
    )
    if not raw:
        return (None, {}) if return_metadata else None
        
    parsed = extract_json(raw)
    if return_metadata:
        return (parsed, {"raw_response": raw})
    return parsed


def chat_json_fast(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 1000,
    reasoning_effort: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Any:
    """빠르고 저렴한 모델을 사용한 JSON 응답. model 미지정 시 chat_model_ctx → gpt-4o-mini 순으로 사용."""
    actual_model = model or chat_model_ctx.get() or "gpt-4o-mini"
    return chat_json(
        system_prompt,
        user_prompt,
        model=actual_model,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url
    )


def chat_stream(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    reasoning_effort: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Generator[str, None, None]:
    """스트리밍 응답 제너레이터. model 미지정 시 chat_model_ctx → CHAT_MODEL 순으로 사용. 파라미터는 context 우선."""
    actual_model = model or chat_model_ctx.get() or CHAT_MODEL
    temp, tok, eff, top_p_val = _resolve_model_params(temperature, max_tokens, reasoning_effort, None)
    client = _get_chat_client(openai_api_key, openai_base_url)
    m_lower = actual_model.lower()
    is_reasoning = "gpt-5" in m_lower or "nano" in m_lower or m_lower.startswith("o1") or m_lower.startswith("o3")

    kwargs: Dict[str, Any] = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
    }
    if not is_reasoning:
        kwargs["temperature"] = temp
        if top_p_val is not None:
            kwargs["top_p"] = top_p_val

    if tok:
        if is_reasoning:
            kwargs["max_completion_tokens"] = tok
        else:
            kwargs["max_tokens"] = tok

    if is_reasoning and eff is not None:
        kwargs["reasoning_effort"] = eff

    try:
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            if chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except Exception as e:
        if _DEBUG:
            print(f"[chat_stream] 스트리밍 오류: {e}", file=sys.stderr)
        raise


def chat_with_metadata(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    reasoning_effort: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """메타데이터(usage 포함)를 포함한 상세 응답. model 미지정 시 chat_model_ctx → CHAT_MODEL 순으로 사용."""
    actual_model = model or chat_model_ctx.get() or CHAT_MODEL
    temp, tok, eff, top_p_val = _resolve_model_params(temperature, max_tokens, reasoning_effort, None)
    client = _get_chat_client(openai_api_key, openai_base_url)
    m_lower = actual_model.lower()
    is_reasoning = "gpt-5" in m_lower or "nano" in m_lower or m_lower.startswith("o1") or m_lower.startswith("o3")

    kwargs: Dict[str, Any] = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if not is_reasoning:
        kwargs["temperature"] = temp
        if top_p_val is not None:
            kwargs["top_p"] = top_p_val
    if tok is not None:
        if is_reasoning:
            kwargs["max_completion_tokens"] = tok
        else:
            kwargs["max_tokens"] = tok
    if is_reasoning and eff is not None:
        kwargs["reasoning_effort"] = eff

    try:
        r = client.chat.completions.create(**kwargs)
        content = ""
        if r.choices:
            raw = r.choices[0].message.content
            content = raw.strip() if raw else ""
        usage = None
        if getattr(r, "usage", None) is not None:
            u = r.usage
            usage = {
                "prompt_tokens": getattr(u, "prompt_tokens", None) or 0,
                "completion_tokens": getattr(u, "completion_tokens", None) or 0,
                "total_tokens": getattr(u, "total_tokens", None) or 0,
            }
        return {
            "content": content,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "model": actual_model,
            "usage": usage,
        }
    except Exception as e:
        actual_api_key = openai_api_key or openai_api_key_ctx.get() or OPENAI_API_KEY
        key_info = f"Used Key: {actual_api_key[:7]}...{actual_api_key[-4:]}" if actual_api_key else "None"
        new_msg = f"{str(e)} | [{key_info}]"
        if _DEBUG:
            print(f"[chat_with_metadata] API 호출 오류: {new_msg}", file=sys.stderr)
        raise Exception(new_msg)
