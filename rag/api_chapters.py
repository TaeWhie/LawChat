# -*- coding: utf-8 -*-
"""
API 동기화된 법령 본문에서 장(章)·조문 목록 추출.
api_data/laws/law/*.json (국가법령정보 API 본문 응답) 파싱.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from config import LAWS_DATA_DIR
except ImportError:
    LAWS_DATA_DIR = Path("api_data/laws")

# 근로기준법 조문 번호 구간 → 장 (API에 장 정보가 없을 때 사용)
LABOR_LAW_CHAPTERS = [
    ("제1장", "총칙", 1, 5),
    ("제2장", "근로계약", 6, 17),
    ("제3장", "임금", 18, 43),
    ("제4장", "근로시간·휴게", 44, 60),
    ("제5장", "해고 등", 61, 72),
    ("제6장", "기술공부생", 73, 76),
    ("제7장", "재해보상", 77, 84),
    ("제8장", "취업규칙", 85, 94),
    ("제9장", "기숙사", 95, 98),
    ("제10장", "검사와 감독", 99, 105),
    ("제11장", "벌칙", 106, 115),
    ("부칙", "부칙", 116, 999),
]


def _article_num_to_int(jo_no: str) -> Optional[int]:
    """조문번호 '1', '2', '36' 등 → int. '36의2' → 36."""
    if not jo_no:
        return None
    s = str(jo_no).strip()
    for i, c in enumerate(s):
        if not c.isdigit():
            if i == 0:
                return None
            return int(s[:i]) if s[:i] else None
    return int(s) if s else None


def _to_str(x: Any) -> str:
    """API 필드값을 문자열로. 리스트면 공백으로 합침."""
    if x is None:
        return ""
    if isinstance(x, list):
        return " ".join(_to_str(t) for t in x).strip()
    return str(x).strip()


def _extract_paragraphs_from_units(units_same_article: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """같은 조문 번호의 조문단위 리스트에서 본문+항+호+목 순서대로 추출. 
    반환: [{type: "본문"|"항"|"호"|"목", num: "①"|"1"|"가"|None, text: "..."}, ...]."""
    paragraphs = []
    for u in units_same_article:
        if not isinstance(u, dict):
            continue
        # 조문 본문(조문내용) - 항이 없을 때만 별도로 표시
        lead = _to_str(u.get("조문내용") or u.get("joContent") or u.get("content"))
        hang_list = u.get("항") or u.get("hang") or []
        if lead and not hang_list:
            paragraphs.append({"type": "본문", "num": None, "text": lead})
        # 항(項) 배열: 항번호(원문자 ①, ②, ③...) + 항내용 + 호(號) 배열
        if isinstance(hang_list, list):
            for h in hang_list:
                if not isinstance(h, dict):
                    continue
                hang_num = _to_str(h.get("항번호") or h.get("hangNo") or "")
                hang_content = _to_str(h.get("항내용") or h.get("hangContent"))
                # 항내용이 있으면 항으로 추가
                if hang_content:
                    paragraphs.append({"type": "항", "num": hang_num if hang_num else None, "text": hang_content})
                # 호(號) 배열: 호번호(숫자 1, 2, 3...) + 호내용 + 목(目) 배열
                ho_list = h.get("호") or h.get("ho") or []
                if isinstance(ho_list, list):
                    for ho in ho_list:
                        if not isinstance(ho, dict):
                            continue
                        ho_num = _to_str(ho.get("호번호") or ho.get("hoNo") or "")
                        ho_content = _to_str(ho.get("호내용") or ho.get("hoContent") or ho.get("content"))
                        if ho_content:
                            paragraphs.append({"type": "호", "num": ho_num if ho_num else None, "text": ho_content})
                        # 목(目) 배열: 목번호(가, 나, 다...) + 목내용
                        mok_list = ho.get("목") or ho.get("mok") or []
                        if isinstance(mok_list, list):
                            for mok in mok_list:
                                if not isinstance(mok, dict):
                                    continue
                                mok_num = _to_str(mok.get("목번호") or mok.get("mokNo") or "")
                                mok_content = _to_str(mok.get("목내용") or mok.get("mokContent") or mok.get("content"))
                                if mok_content:
                                    paragraphs.append({"type": "목", "num": mok_num if mok_num else None, "text": mok_content})
    return paragraphs


def _find_law_body_dir() -> Path:
    return LAWS_DATA_DIR / "law"


def _load_law_body(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_law_name_from_body(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("법령", "law", "LawService"):
        val = data.get(key)
        if isinstance(val, dict):
            info = val.get("기본정보") or val.get("basicInfo") or val
            name = (info.get("법령명_한글") or info.get("법령명한글") or info.get("법령명") or "").strip()
            if name:
                return name
    return ""


def _parse_jo_mun_unit(body: Any) -> List[Dict[str, Any]]:
    """법령.조문.조문단위 배열 추출 (국가법령정보 API JSON 구조)."""
    if not isinstance(body, dict):
        return []
    for key in ("법령", "law", "LawService"):
        val = body.get(key)
        if isinstance(val, dict):
            jo = val.get("조문") or val.get("jo")
            if isinstance(jo, dict):
                units = jo.get("조문단위") or jo.get("article") or jo.get("list")
                if isinstance(units, list) and units:
                    return units
    return []


def _find_geunro_body_path() -> Optional[Path]:
    """api_data/laws/law/ 에서 근로기준법 본문 JSON 경로 반환 (법령명 한글 기준)."""
    law_dir = _find_law_body_dir()
    if not law_dir.exists():
        return None
    for path in law_dir.glob("*.json"):
        if path.name == "list.json":
            continue
        data = _load_law_body(path)
        if not data:
            continue
        name = _get_law_name_from_body(data)
        if name and "근로기준법" in name and "시행" not in name:
            return path
    return None


def get_chapters_from_api() -> List[Dict[str, Any]]:
    """API 동기화된 근로기준법 본문에서 장 목록 반환. 없으면 빈 리스트."""
    import sys
    path = _find_geunro_body_path()
    if not path:
        print("[get_chapters_from_api] api_data/laws/law에서 근로기준법 본문 JSON을 찾을 수 없습니다. sync_laws를 실행하세요.", file=sys.stderr)
        return []
    data = _load_law_body(path)
    if not data:
        print(f"[get_chapters_from_api] {path}를 읽을 수 없습니다.", file=sys.stderr)
        return []
    units = _parse_jo_mun_unit(data)
    if not units:
        print(f"[get_chapters_from_api] {path}에서 조문단위를 추출할 수 없습니다. JSON 구조를 확인하세요.", file=sys.stderr)
        return []
    # 근로기준법 장 구간으로 장 목록 반환
    return [
        {"number": num, "title": title, "order": order}
        for order, (num, title, _start, _end) in enumerate(LABOR_LAW_CHAPTERS, 1)
    ]


def get_articles_by_chapter_from_api(chapter_number: str) -> Optional[List[Dict[str, Any]]]:
    """API 동기화된 근로기준법 본문에서 해당 장의 조문 목록 반환. 본문 없으면 None."""
    import sys
    path = _find_geunro_body_path()
    if not path:
        print(f"[get_articles_by_chapter_from_api] api_data/laws/law에서 근로기준법 본문 JSON을 찾을 수 없습니다 (장: {chapter_number}). sync_laws를 실행하세요.", file=sys.stderr)
        return None
    data = _load_law_body(path)
    if not data:
        print(f"[get_articles_by_chapter_from_api] {path}를 읽을 수 없습니다 (장: {chapter_number}).", file=sys.stderr)
        return None
    units = _parse_jo_mun_unit(data)
    if not units:
        print(f"[get_articles_by_chapter_from_api] {path}에서 조문단위를 추출할 수 없습니다 (장: {chapter_number}). JSON 구조를 확인하세요.", file=sys.stderr)
        return None

    # 장 번호 → (start, end) 조문 번호 구간
    chapter_ranges = {}
    for num, title, start, end in LABOR_LAW_CHAPTERS:
        chapter_ranges[num] = (start, end)

    # 실제 조문만 사용 (조문여부 '전문'은 장 제목 등)
    units = [u for u in units if isinstance(u, dict) and (u.get("조문여부") or "").strip() == "조문"]
    start, end = chapter_ranges.get(chapter_number, (-1, -1))
    # 같은 조문 번호+가지번호끼리 묶기 (제43조와 제43조의2는 별도 조문)
    by_article: Dict[str, List[Dict[str, Any]]] = {}
    for u in units:
        if not isinstance(u, dict):
            continue
        jo_no = u.get("조문번호") or u.get("joNo") or ""
        jo_gaji = u.get("조문가지번호") or u.get("joGajiNo") or ""
        n = _article_num_to_int(jo_no)
        # 제43조의2 같은 경우: 조문번호="43", 조문가지번호="2" → "제43조의2"
        article_key = f"제{jo_no}조"
        if jo_gaji:
            article_key += f"의{jo_gaji}"
        if chapter_number == "부칙":
            if n is not None and n >= 116:
                by_article.setdefault(article_key, []).append(u)
        elif n is not None and start >= 0 and start <= n <= end:
            by_article.setdefault(article_key, []).append(u)
    result = []
    def _sort_key(item):
        k = item[0]
        # "제43조의2" → (43, 2), "제43조" → (43, 0)
        base = k.replace("제", "").replace("조", "")
        if "의" in base:
            parts = base.split("의")
            n = _article_num_to_int(parts[0])
            gaji = _article_num_to_int(parts[1]) if len(parts) > 1 else 0
            return (n or 0, gaji or 0, k)
        else:
            n = _article_num_to_int(base)
            return (n or 0, 0, k)
    for article_key, group in sorted(by_article.items(), key=_sort_key):
        first = group[0]
        title = (first.get("조문제목") or first.get("joTitle") or "").strip()
        jo_no = first.get("조문번호") or first.get("joNo") or ""
        jo_gaji = first.get("조문가지번호") or first.get("joGajiNo") or ""
        display_num = f"제{jo_no}조"
        if jo_gaji:
            display_num += f"의{jo_gaji}"
        paragraphs = _extract_paragraphs_from_units(group)
        result.append({
            "article_number": article_key,
            "title": title or display_num,
            "paragraphs": paragraphs,
        })
    return result
