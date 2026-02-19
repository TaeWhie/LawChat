# -*- coding: utf-8 -*-
"""
국가법령정보 공동활용 API 클라이언트.

중요: 서버가 봇으로 인식하면 HTML 에러(미신청된 목록/본문 등)를 반환하므로,
모든 요청에 반드시 브라우저와 동일한 헤더를 포함한다.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

try:
    from config import LAW_API_OC, LAW_API_DELAY_SEC, LAW_API_TIMEOUT, LAW_EFFECTIVE_YEAR
except ImportError:
    LAW_API_OC = ""
    LAW_API_DELAY_SEC = 1.0
    LAW_API_TIMEOUT = 30
    LAW_EFFECTIVE_YEAR = None

# 목록/검색은 lawSearch.do, 본문·일부 연계 API는 lawService.do
BASE_URL_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
BASE_URL_SERVICE = "https://www.law.go.kr/DRF/lawService.do"

# 연계 API(lstrmRlt, dlytrmRlt, lstrmRltJo, joRltLstrm)는 lawService.do 사용
TARGETS_USE_SERVICE = frozenset({"lstrmRlt", "dlytrmRlt", "lstrmRltJo", "joRltLstrm"})
# joRltLstrm은 조문번호 JO 파라미터 사용
TARGET_USES_JO = "joRltLstrm"

# 봇 차단 방지: 모든 요청에 필수. 제거 시 노동위원회·고용보험심사위원회 등에서 HTML 에러 발생
# 최신 브라우저 헤더로 업데이트 및 추가 헤더 포함
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://open.law.go.kr/",
    "Origin": "https://open.law.go.kr",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# 세션 재사용으로 쿠키 유지 (봇 차단 완화)
_session = None

def _get_session():
    """세션 재사용으로 쿠키 유지"""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(BROWSER_HEADERS)
    return _session


def _ensure_oc(oc: Optional[str] = None) -> str:
    if oc is not None and oc:
        return oc
    if LAW_API_OC:
        return LAW_API_OC
    raise ValueError("LAW_API_OC가 설정되지 않았습니다. config 또는 환경변수 LAW_API_OC를 설정하세요.")


def _delay() -> None:
    """요청 간 딜레이. 봇 차단 방지를 위해 랜덤 딜레이 추가"""
    import random
    if LAW_API_DELAY_SEC > 0:
        # 기본 딜레이 + 랜덤 추가 (0.5~1.5초)
        delay = LAW_API_DELAY_SEC + random.uniform(0.5, 1.5)
        time.sleep(delay)


def search_list(
    target: str,
    query: Optional[str] = None,
    *,
    display: int = 20,
    page: int = 1,
    jo: Optional[str] = None,
    ef_yd: Optional[str] = None,
    oc: Optional[str] = None,
    output_type: str = "JSON",
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    목록/검색 API 호출 (lawSearch.do 또는 lawService.do).

    - target: API 종류 (law, prec, lstrmAI, aiSearch, lstrmRlt 등)
    - query: 검색어 (목록 API 대부분)
    - jo: 조문번호 (joRltLstrm 전용)
    - ef_yd: 시행일자 범위 (예: 20240101~20241231). target=law일 때 지정하면 target=eflaw로 요청
    - 연계 API(lstrmRlt, dlytrmRlt, lstrmRltJo, joRltLstrm)는 자동으로 lawService.do 사용
    """
    oc_key = _ensure_oc(oc)
    use_service = target in TARGETS_USE_SERVICE
    base_url = BASE_URL_SERVICE if use_service else BASE_URL_SEARCH

    # 연도 설정(LAW_EFFECTIVE_YEAR) 또는 ef_yd가 있으면 법령은 시행일 기준(eflaw)으로 조회
    use_eflaw = (target == "law" and (ef_yd or (LAW_EFFECTIVE_YEAR and not use_service)))
    actual_target = "eflaw" if use_eflaw else target
    if use_eflaw and not ef_yd and LAW_EFFECTIVE_YEAR:
        ef_yd = f"{LAW_EFFECTIVE_YEAR}0101~{LAW_EFFECTIVE_YEAR}1231"

    params: Dict[str, Any] = {
        "OC": oc_key,
        "target": actual_target,
        "type": output_type,
    }
    if target == TARGET_USES_JO and jo is not None:
        params["JO"] = jo
    elif query:
        params["query"] = query
    if ef_yd:
        params["efYd"] = ef_yd

    if not use_service:
        params["display"] = display
        params["page"] = page

    _delay()
    to = timeout if timeout is not None else LAW_API_TIMEOUT
    session = _get_session()
    resp = session.get(base_url, params=params, timeout=to)

    if resp.status_code != 200:
        return {
            "success": False,
            "error": f"HTTP {resp.status_code}",
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type", ""),
        }

    ct = resp.headers.get("Content-Type", "")
    if "application/json" not in ct and "text/plain" not in ct:
        if "text/html" in ct:
            return {
                "success": False,
                "error": "HTML response (possible bot block)",
                "status_code": resp.status_code,
                "content_type": ct,
                "response_preview": resp.text[:500],
            }
        # 일부 서버가 Content-Type을 안 주는 경우 JSON 파싱 시도
    try:
        data = resp.json()
    except Exception as e:
        return {
            "success": False,
            "error": f"JSON decode: {e!s}",
            "status_code": resp.status_code,
            "content_type": ct,
            "response_preview": resp.text[:500],
        }

    return {
        "success": True,
        "data": data,
        "status_code": resp.status_code,
        "content_type": ct,
    }


def get_body(
    target: str,
    id: str,
    *,
    mst: Optional[str] = None,
    ef_yd: Optional[str] = None,
    oc: Optional[str] = None,
    output_type: str = "JSON",
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    본문 조회 (lawService.do). 판례·법령·해석례·위원회 등 ID로 본문 조회.
    target=law 일 때 mst(법령일련번호)를 넘기면 MST 파라미터로 요청해 올바른 법령 본문 조회.
    target=law이고 LAW_EFFECTIVE_YEAR/ef_yd가 있으면 target=eflaw로 시행일 기준 본문 조회.
    """
    oc_key = _ensure_oc(oc)
    use_eflaw = target == "law" and (ef_yd or LAW_EFFECTIVE_YEAR)
    actual_target = "eflaw" if use_eflaw else target
    if use_eflaw and not ef_yd and LAW_EFFECTIVE_YEAR:
        ef_yd = f"{LAW_EFFECTIVE_YEAR}1231"  # 해당 연도 말일 기준 시행법령

    params = {
        "OC": oc_key,
        "target": actual_target,
        "type": output_type,
    }
    if ef_yd:
        params["efYd"] = ef_yd
    if actual_target == "law" or actual_target == "eflaw":
        if mst:
            params["MST"] = mst
        else:
            params["ID"] = id
    else:
        params["ID"] = id
    _delay()
    to = timeout if timeout is not None else LAW_API_TIMEOUT
    session = _get_session()
    resp = session.get(BASE_URL_SERVICE, params=params, timeout=to)

    if resp.status_code != 200:
        return {
            "success": False,
            "error": f"HTTP {resp.status_code}",
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type", ""),
        }

    ct = resp.headers.get("Content-Type", "")
    if "application/json" not in ct and "text/plain" not in ct:
        if "text/html" in ct:
            return {
                "success": False,
                "error": "HTML response (possible bot block)",
                "status_code": resp.status_code,
                "content_type": ct,
                "response_preview": resp.text[:500],
            }
    try:
        data = resp.json()
    except Exception as e:
        return {
            "success": False,
            "error": f"JSON decode: {e!s}",
            "status_code": resp.status_code,
            "content_type": ct,
            "response_preview": resp.text[:500],
        }

    return {
        "success": True,
        "data": data,
        "status_code": resp.status_code,
        "content_type": ct,
    }
