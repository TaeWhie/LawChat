# -*- coding: utf-8 -*-
"""
aiSearch / aiRltLs 등 온디맨드 API 호출 결과를 쿼리·조문 키 기준으로 파일 캐시.
캐시에 있으면 API 호출 없이 로드, 없으면 1회 호출 후 저장.
Streamlit 등 실행 경로(cwd)와 무관하게 프로젝트 루트 기준 절대 경로 사용.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

def _cache_dir() -> Path:
    """캐시 디렉터리(절대 경로). config 또는 이 파일 기준 프로젝트 루트 사용."""
    try:
        from config import CACHE_DIR
        return Path(CACHE_DIR).resolve()
    except ImportError:
        return (Path(__file__).resolve().parent.parent / "api_data" / "cache").resolve()


def _cache_key(s: str, max_len: int = 120) -> str:
    """캐시 파일명용 안전 키. 길면 해시 사용."""
    safe = "".join(c if c.isalnum() or c in ("_", "-", " ") else "_" for c in (s or ""))
    safe = safe.strip().replace(" ", "_")[:max_len]
    if len(safe) >= max_len or not safe:
        return hashlib.md5((s or "").encode("utf-8")).hexdigest()
    return safe or hashlib.md5((s or "").encode("utf-8")).hexdigest()


def _load_cached(path: Path) -> Optional[Dict[str, Any]]:
    from rag.sync_common import load_json
    if not path.exists():
        return None
    return load_json(path)


def _save_cached(path: Path, data: Dict[str, Any]) -> None:
    from rag.sync_common import save_json
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(path, data)


def get_aiSearch_cached(query: str) -> Dict[str, Any]:
    """
    지능형 검색(aiSearch) 결과. 캐시에 있으면 반환, 없으면 API 호출 후 저장하고 반환.
    LAW_API_OC가 없거나 API 실패 시 빈 결과를 반환해 호출 측이 크래시하지 않도록 함.
    """
    key = _cache_key(query)
    cache_dir = _cache_dir() / "aiSearch"
    path = cache_dir / f"{key}.json"
    data = _load_cached(path)
    if data is not None and data.get("success") is not False:
        return data
    try:
        from rag.law_api_client import search_list
        r = search_list("aiSearch", query=query, display=20, page=1)
        if r.get("success") and r.get("data"):
            _save_cached(path, r)
        return r
    except (ValueError, Exception):
        # LAW_API_OC 미설정 또는 네트워크/API 오류 시 빈 결과 반환
        return {"success": False, "data": None}


def get_aiRltLs_cached(article_key: str) -> Dict[str, Any]:
    """
    연관법령(aiRltLs) 결과. 조문 키(예: 근로기준법 제34조) 기준 캐시.
    LAW_API_OC가 없거나 API 실패 시 빈 결과를 반환해 호출 측이 크래시하지 않도록 함.
    """
    key = _cache_key(article_key)
    cache_dir = _cache_dir() / "aiRltLs"
    path = cache_dir / f"{key}.json"
    data = _load_cached(path)
    if data is not None and data.get("success") is not False:
        return data
    try:
        from rag.law_api_client import search_list
        r = search_list("aiRltLs", query=article_key, display=20, page=1)
        if r.get("success") and r.get("data"):
            _save_cached(path, r)
        return r
    except (ValueError, Exception):
        # LAW_API_OC 미설정 또는 네트워크/API 오류 시 빈 결과 반환
        return {"success": False, "data": None}
