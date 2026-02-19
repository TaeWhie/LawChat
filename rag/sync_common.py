# -*- coding: utf-8 -*-
"""
API 동기화 스크립트 공통: 디렉터리 생성, JSON 저장/로드.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_list_from_response(data: Dict[str, Any], target: str) -> list:
    """API 목록 응답에서 항목 리스트 추출. 다양한 응답 루트 키 대응."""
    if not isinstance(data, dict):
        return []
    candidates = (
        (target,)  # target과 일치하는 키 우선 (law, admrul, prec 등)
        + (
            "law", "admrul", "prec", "expc", "detc", "decc",
            "licbyl", "admbyl", "ppc", "eiac", "ftc", "nlrc", "iaciac",
            "moelCgmExpc", "molegCgmExpc", "mojCgmExpc",
            "lstrmAI", "dlytrm", "lsRlt", "lstrmRlt", "dlytrmRlt",
            "lstrmRltJo", "joRltLstrm", "aiSearch", "aiRltLs",
        )
    )
    for key in list(data.keys()):
        val = data.get(key)
        if isinstance(val, dict):
            for sub in candidates:
                if sub in val and isinstance(val[sub], list):
                    return val[sub]
            if "list" in val and isinstance(val["list"], list):
                return val["list"]
    return []


def extract_id_from_item(item: Any, target: str) -> Optional[str]:
    """목록 항목에서 본문 조회용 ID 추출."""
    if not isinstance(item, dict):
        return None
    for key in ("id", "ID", "법령ID", "판례일련번호", "일련번호", "법령해석일련번호"):
        if key in item and item[key] is not None:
            return str(item[key]).strip()
    return None


def extract_mst_from_law_item(item: Any) -> Optional[str]:
    """법령 목록 항목에서 본문 조회용 법령일련번호(MST) 추출. target=law 본문은 MST로 요청해야 올바른 법령 반환."""
    if not isinstance(item, dict):
        return None
    mst = item.get("법령일련번호") or item.get("법령일련번호 ")
    if mst is not None:
        return str(mst).strip()
    return None
