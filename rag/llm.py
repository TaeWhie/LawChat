# GPT-5-nano 호출 및 JSON 파싱
import json
import os
import re
import sys
from typing import Any, Dict, Generator, List, Optional

from openai import OpenAI

from config import CHAT_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL
from rag.context import openai_api_key_ctx, openai_base_url_ctx

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
    
    # 캐시 키 생성 (키와 베이스 URL 조합)
    cache_key = f"{actual_api_key}|{actual_base_url}"
    
    if cache_key not in _clients:
        kwargs: dict = {"api_key": actual_api_key}
        if actual_base_url:
            kwargs["base_url"] = actual_base_url
        _clients[cache_key] = OpenAI(**kwargs)
        
    return _clients[cache_key]


def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = CHAT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> str:
    """기본 채팅 응답."""
    client = _get_chat_client(openai_api_key, openai_base_url)
    is_reasoning = "gpt-5" in model or "nano" in model.lower()
    
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }

    if max_tokens is not None:
        if model.startswith("o1") or model.startswith("o3"):
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

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
    model: str = CHAT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    return_metadata: bool = False,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Any:
    """JSON 모드 응답."""
    raw = chat(
        system_prompt, 
        user_prompt, 
        model=model, 
        temperature=temperature, 
        max_tokens=max_tokens,
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
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 1000,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Any:
    """빠르고 저렴한 모델을 사용한 JSON 응답."""
    return chat_json(
        system_prompt,
        user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url
    )


def chat_stream(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = CHAT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Generator[str, None, None]:
    """스트리밍 응답 제너레이터."""
    client = _get_chat_client(openai_api_key, openai_base_url)
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": True,
    }
    if max_tokens:
        if model.startswith("o1") or model.startswith("o3"):
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

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
    model: str = CHAT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 2000,
    openai_api_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """메타데이터를 포함한 상세 응답."""
    content = chat(
        system_prompt, 
        user_prompt, 
        model=model, 
        temperature=temperature, 
        max_tokens=max_tokens,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url
    )
    return {
        "content": content,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "model": model
    }
