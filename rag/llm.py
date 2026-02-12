# GPT-5-nano 호출 및 JSON 파싱
import json
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import CHAT_MODEL, OPENAI_API_KEY


def chat(
    system: str,
    user: str,
    model: str = CHAT_MODEL,
    temperature: float = 0.1,
) -> str:
    """단일 대화 턴. 응답 텍스트 반환."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return (r.choices[0].message.content or "").strip()


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


def chat_json(system: str, user: str) -> Optional[Any]:
    """채팅 후 응답에서 JSON 파싱."""
    raw = chat(system, user)
    return extract_json(raw)
