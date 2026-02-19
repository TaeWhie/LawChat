# -*- coding: utf-8 -*-
"""
api_data/ 에 저장된 API 응답을 RAG용 청크로 로드.

- 법령/행정규칙 본문: api_data/laws/law/*.json, laws/admrul/*.json
- 저장 형식은 law_api_client.get_body() 응답 그대로 (국가법령정보 API JSON 구조)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from config import (
        LAWS_DATA_DIR,
        SOURCE_LAW,
        SOURCE_DECREE,
        SOURCE_RULE,
        SOURCE_MIN_WAGE_LAW,
        SOURCE_RETIREMENT_LAW,
        SOURCE_GENDER_EQUALITY_LAW,
        SOURCE_PART_TIME_LAW,
        SOURCE_UNION_LAW,
        SOURCE_PARTICIPATION_LAW,
        SOURCE_SAFETY_LAW,
        SOURCE_EMPLOYMENT_INSURANCE_LAW,
        SOURCE_JOB_STABILITY_LAW,
        SOURCE_INDUSTRIAL_ACCIDENT_LAW,
    )
except ImportError:
    LAWS_DATA_DIR = Path("api_data/laws")
    SOURCE_LAW = "근로기준법(법률)"
    SOURCE_DECREE = "근로기준법(시행령)"
    SOURCE_RULE = "근로기준법(시행규칙)"
    SOURCE_MIN_WAGE_LAW = "최저임금법(법률)"
    SOURCE_RETIREMENT_LAW = "근로자퇴직급여 보장법(법률)"
    SOURCE_GENDER_EQUALITY_LAW = "남녀고용평등과 일·가정 양립 지원에 관한 법률(법률)"
    SOURCE_PART_TIME_LAW = "기간제 및 단시간근로자 보호 등에 관한 법률(법률)"
    SOURCE_UNION_LAW = "노동조합 및 노동관계조정법(법률)"
    SOURCE_PARTICIPATION_LAW = "근로자참여 및 협력증진에 관한 법률(법률)"
    SOURCE_SAFETY_LAW = "산업안전보건법(법률)"
    SOURCE_EMPLOYMENT_INSURANCE_LAW = "고용보험법(법률)"
    SOURCE_JOB_STABILITY_LAW = "직업안정법(법률)"
    SOURCE_INDUSTRIAL_ACCIDENT_LAW = "산업재해보상보험법(법률)"


def _find_articles_in_law_body(data: Any) -> List[Dict[str, Any]]:
    """법령 본문 JSON에서 조문 배열 추출. 국가법령정보 API: 법령.조문.조문단위 구조 대응."""
    if not isinstance(data, dict):
        return []
    # 국가법령정보 응답: 루트에 "법령" 키가 있으면 그 안에서 조문단위 탐색
    inner = data.get("법령") if isinstance(data.get("법령"), dict) else None
    if inner is not None:
        jo = inner.get("조문")
        if isinstance(jo, dict) and "조문단위" in jo:
            u = jo["조문단위"]
            if isinstance(u, list) and u and isinstance(u[0], dict):
                return u
        if isinstance(jo, list) and jo and isinstance(jo[0], dict):
            return jo
    for key in list(data.keys()):
        val = data[key]
        if not isinstance(val, dict):
            continue
        for sub in ("조문", "jo", "article", "articles", "law", "admrul"):
            if sub not in val:
                continue
            v = val[sub]
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
            if isinstance(v, dict) and "조문단위" in v:
                u = v["조문단위"]
                if isinstance(u, list) and u and isinstance(u[0], dict):
                    return u
        for k2, v2 in val.items():
            if isinstance(v2, list) and v2 and isinstance(v2[0], dict):
                for item in v2:
                    if isinstance(item, dict) and (
                        "조문내용" in item or "조문제목" in item or "항내용" in item
                    ):
                        return v2
    return []


# 장(章) 제목만 있는 항목인지 판별 (제1장 총칙, 제3장 임금 등 → 조문이 아니므로 제외)
_CHAPTER_HEADER_RE = re.compile(r"^\s*제\s*\d+\s*장\s")


def _is_chapter_header(item: Dict[str, Any]) -> bool:
    """조문단위가 '제N장 ...' 장 제목만 있는지 여부."""
    raw = (item.get("조문내용") or item.get("joContent") or item.get("content") or "").strip()
    if not raw:
        return False
    return bool(_CHAPTER_HEADER_RE.match(raw))


def _to_str(val: Any) -> str:
    """API 응답이 문자열 또는 리스트(문자열 배열)일 수 있으므로 통일해 문자열로 반환."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        return " ".join(_to_str(x) for x in val).strip()
    return str(val).strip() if val else ""


def _collect_article_text(item: Dict[str, Any]) -> str:
    """조문 1개의 전문 텍스트 수집. 조문내용 + 항(항내용, 호내용) 병합."""
    parts = []
    content = _to_str(item.get("조문내용") or item.get("joContent") or item.get("content"))
    # 장 제목만 있으면 본문으로 쓰지 않음 (이 경우 청크 자체를 스킵함)
    if content and not _CHAPTER_HEADER_RE.match(content):
        parts.append(content)
    # 항(項) 배열: 항내용 + 호(號) 호내용
    hang_list = item.get("항") or item.get("hang") or []
    if isinstance(hang_list, list):
        for hang in hang_list:
            if not isinstance(hang, dict):
                continue
            hang_content = _to_str(hang.get("항내용") or hang.get("호내용"))
            if hang_content:
                parts.append(hang_content)
            for ho in (hang.get("호") or []) if isinstance(hang.get("호"), list) else []:
                if isinstance(ho, dict):
                    ho_content = _to_str(ho.get("호내용") or ho.get("content"))
                    if ho_content:
                        parts.append(ho_content)
    text = "\n".join(p for p in parts if p).strip()
    return text


def _article_to_chunk(
    item: Dict[str, Any],
    source_label: str,
    chapter_hint: str = "",
) -> Dict[str, Any]:
    """조문 항목 1개를 벡터 스토어 청크 형식으로 변환. 본문은 조문내용 + 항(항내용/호내용) 병합."""
    num = item.get("조문번호") or item.get("joNo") or item.get("articleNo") or ""
    sub = item.get("조문가지번호") or item.get("joGajiNo") or ""
    title = item.get("조문제목") or item.get("joTitle") or ""
    article_title = f"제{num}조"
    if sub:
        article_title += f"의{sub}"
    if title:
        article_title += f" {title}"
    text = _collect_article_text(item).strip() or article_title
    embedding_text = f"[{chapter_hint}] {article_title}\n{text}" if chapter_hint else text
    return {
        "text": text,
        "embedding_text": embedding_text,
        "source": source_label,
        "article": article_title,
        "kind": "[본문]",
        "section": "본칙",
    }


def _load_json(path: Path) -> Any:
    import json
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_source(raw_name: str, target: str) -> str:
    """파이프라인 filter_sources(SOURCE_LAW 등)와 맞추기 위해 법령명 정규화."""
    if not raw_name:
        return raw_name
    # 시행령/시행규칙 먼저 처리
    if "시행령" in raw_name:
        return SOURCE_DECREE if "근로기준법" in raw_name else raw_name + "(시행령)" if "(시행령)" not in raw_name else raw_name
    if "시행규칙" in raw_name:
        return SOURCE_RULE if "근로기준법" in raw_name else raw_name + "(시행규칙)" if "(시행규칙)" not in raw_name else raw_name
    if target == "admrul":
        return raw_name
    # 법률 정규화: config.ALL_LABOR_LAW_SOURCES와 동일한 상수로 반환 (모든 노동법 동일 처리)
    if target == "law":
        # 이미 (법률) 접미사가 있으면 config 상수와 일치하는지 확인 후 반환
        if "(법률)" in raw_name:
            return raw_name
        # ALL_LABOR_LAW_SOURCES에 대응하는 법률명 매핑 (상수 사용으로 검색 필터와 항상 일치)
        if "근로기준법" in raw_name and "시행" not in raw_name:
            return SOURCE_LAW
        if "최저임금법" in raw_name:
            return SOURCE_MIN_WAGE_LAW
        if "근로자퇴직급여 보장법" in raw_name or "근로자퇴직급여보장법" in raw_name:
            return SOURCE_RETIREMENT_LAW
        if "남녀고용평등" in raw_name or "일·가정 양립" in raw_name:
            return SOURCE_GENDER_EQUALITY_LAW
        if "기간제 및 단시간근로자" in raw_name or "기간제근로자" in raw_name:
            return SOURCE_PART_TIME_LAW
        if "노동조합 및 노동관계조정법" in raw_name or "노동조합법" in raw_name:
            return SOURCE_UNION_LAW
        if "근로자참여 및 협력증진" in raw_name:
            return SOURCE_PARTICIPATION_LAW
        if "산업안전보건법" in raw_name:
            return SOURCE_SAFETY_LAW
        if "고용보험법" in raw_name:
            return SOURCE_EMPLOYMENT_INSURANCE_LAW
        if "직업안정법" in raw_name:
            return SOURCE_JOB_STABILITY_LAW
        if "산업재해보상보험법" in raw_name:
            return SOURCE_INDUSTRIAL_ACCIDENT_LAW
        # 기타 법률: (법률) 접미사 추가
        return raw_name + "(법률)"
    return raw_name


def _find_law_name_in_dict(d: Dict[str, Any]) -> str:
    """dict에서 법령명 키만 검사 (재귀용)."""
    for name_key in ("법령명_한글", "법령명한글", "법령명", "lawNm", "규정명"):
        if name_key in d and d[name_key]:
            return str(d[name_key]).strip()
    return ""


def _get_law_name_from_body(data: Any) -> str:
    """본문 JSON에서 법령명 한글 추출. 국가법령정보: 법령.기본정보.법령명_한글 등.
    구조가 깊어도 재귀 탐색으로 법령명_한글/법령명한글을 찾음."""
    if not isinstance(data, dict):
        return ""
    # 1단계: 루트 바로 아래에서 법령명 찾기
    for key in list(data.keys()):
        val = data.get(key)
        if isinstance(val, dict):
            name = _find_law_name_in_dict(val)
            if name:
                return name
            # 2단계: 기본정보/기본정보단위 등 한 단계 더 들어가서 찾기
            for sub in ("기본정보", "기본정보단위", "법령기본정보"):
                info = val.get(sub)
                if isinstance(info, dict):
                    name = _find_law_name_in_dict(info)
                    if name:
                        return name
    # 3단계: 재귀 탐색 (기본정보가 더 깊은 경우 대비, 깊이 제한)
    found = _get_law_name_from_body_recursive(data, max_depth=10)
    return found or ""


def _get_law_name_from_body_recursive(node: Any, depth: int = 0, max_depth: int = 10) -> str:
    """JSON 트리에서 법령명_한글/법령명한글 재귀 탐색."""
    if depth > max_depth:
        return ""
    if isinstance(node, dict):
        name = _find_law_name_in_dict(node)
        if name:
            return name
        for v in node.values():
            found = _get_law_name_from_body_recursive(v, depth + 1, max_depth)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _get_law_name_from_body_recursive(item, depth + 1, max_depth)
            if found:
                return found
    return ""


def _get_law_name_from_list_json(dir_path: Path, mst: str) -> str:
    """list.json에서 법령일련번호(MST)로 법령명한글 조회. 동기화 시 검색 결과에 있으면 사용."""
    list_path = dir_path / "list.json"
    if not list_path.exists():
        return ""
    data = _load_json(list_path)
    if not isinstance(data, dict):
        return ""
    search_node = data.get("LawSearch") or data.get("lawSearch")
    if not isinstance(search_node, dict):
        return ""
    laws = search_node.get("law")
    if not isinstance(laws, list):
        return ""
    for item in laws:
        if not isinstance(item, dict):
            continue
        if str(item.get("법령일련번호") or "").strip() == str(mst).strip():
            name = (item.get("법령명한글") or item.get("법령명_한글") or "").strip()
            if name:
                return name
    return ""


def _flatten_body_to_text(data: Any, max_len: int = 50000) -> str:
    """구조화된 본문에서 텍스트만 재귀적으로 이어 붙임."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        parts = []
        for k, v in data.items():
            if k in ("조문내용", "조문제목", "항내용", "joContent", "content"):
                if v:
                    parts.append(str(v))
            else:
                parts.append(_flatten_body_to_text(v, max_len))
        return "\n\n".join(p for p in parts if p)[:max_len]
    if isinstance(data, list):
        return "\n\n".join(_flatten_body_to_text(x, max_len) for x in data)[:max_len]
    return ""


def load_chunks_from_api_laws(laws_data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """api_data/laws/law/, laws/admrul/ 아래 본문 JSON을 읽어 조 단위 청크 리스트 반환.
    list.json은 제외. store/build_vector_store에서 사용하는 청크 스키마."""
    base = laws_data_dir or LAWS_DATA_DIR
    chunks: List[Dict[str, Any]] = []
    for target in ("law", "admrul"):
        dir_path = base / target
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.json"):
            if path.name == "list.json":
                continue
            data = _load_json(path)
            if not data:
                continue
            articles = _find_articles_in_law_body(data)
            # 법령명: 응답 내에서 추출, 없으면 list.json에서 MST→법령명, 최후에 target_stem
            raw_name = _get_law_name_from_body(data)
            if not raw_name and path.stem.isdigit():
                raw_name = _get_law_name_from_list_json(dir_path, path.stem)
            raw_name = raw_name or f"{target}_{path.stem}"
            source_label = _normalize_source(raw_name, target)
            if articles:
                for item in articles:
                    if _is_chapter_header(item):
                        continue
                    chunk = _article_to_chunk(item, source_label)
                    chunks.append(chunk)
            else:
                # 조문 배열이 없으면 전체를 한 청크로
                text = _flatten_body_to_text(data)
                if text:
                    chunks.append({
                        "text": text,
                        "embedding_text": text,
                        "source": source_label,
                        "article": path.stem,
                        "kind": "[본문]",
                        "section": "본칙",
                    })
    return chunks


# 상담 시 저장 데이터 우선 읽기용
def load_terms_cached(terms_data_dir: Path, target: str, query: str) -> Any:
    """api_data/terms/ 에서 target+query에 해당하는 저장 파일이 있으면 로드."""
    from rag.sync_common import load_json
    safe = query.replace(" ", "_")
    for name in (f"{target}_{safe}.json", f"{target}.json"):
        path = terms_data_dir / name
        data = load_json(path)
        if data:
            return data
    return None


def load_precedent_cached(precedents_data_dir: Path, target: str, keyword: str) -> Any:
    """api_data/precedents/{target}/by_keyword/{keyword}.json 이 있으면 로드."""
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_data_dir / target / "by_keyword" / f"{safe}.json"
    return load_json(path)


# 상담 시 저장 데이터 우선 사용 (config 경로 사용)
def get_terms_for_consult(target: str, query: str) -> Any:
    """상담 중 용어 데이터가 필요할 때 api_data/terms 캐시에서만 로드. API 호출 없음."""
    try:
        from config import TERMS_DATA_DIR
    except ImportError:
        return None
    return load_terms_cached(TERMS_DATA_DIR, target, query)


def get_precedent_for_consult(target: str, keyword: str) -> Any:
    """상담 중 판례 등 목록이 필요할 때 api_data/precedents 캐시에서만 로드. API 호출 없음."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return None
    return load_precedent_cached(PRECEDENTS_DATA_DIR, target, keyword)


def get_law_terms_from_dlytrmRlt_cache(situation: str) -> List[str]:
    """
    api_data/related/ 의 dlytrmRlt_*.json 캐시에서, 상황 문장에 등장하는 일상용어에 대응하는
    법령용어를 수집해 반환. 이슈 분류 전 쿼리 확장용 (step1 연동).
    """
    try:
        from config import RELATED_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    if not (situation and situation.strip()):
        return []
    related_dir = Path(RELATED_DATA_DIR)
    if not related_dir.exists():
        return []
    law_terms = []
    for path in related_dir.glob("dlytrmRlt_*.json"):
        # dlytrmRlt_월급.json -> "월급"
        stem = path.stem
        if not stem.startswith("dlytrmRlt_"):
            continue
        keyword = stem[len("dlytrmRlt_"):].replace("_", " ")
        if keyword not in situation:
            continue
        data = load_json(path)
        if not data or not isinstance(data, dict):
            continue
        items = extract_list_from_response(data, "dlytrmRlt")
        for item in items:
            if not isinstance(item, dict):
                continue
            term = (
                item.get("법령용어") or item.get("법령용어명")
                or item.get("lawTerm") or item.get("용어")
                or item.get("한글용어")
            )
            if term and isinstance(term, str) and (term := term.strip()):
                law_terms.append(term)
    return list(dict.fromkeys(law_terms))


def get_daily_terms_from_lstrmRlt_cache(law_term: str) -> List[str]:
    """
    api_data/terms/ 의 lstrmRlt_*.json 캐시에서, 법령용어에 대응하는 일상용어를 수집해 반환.
    역방향 확장용 (법령용어 → 일상용어).
    """
    try:
        from config import TERMS_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    if not (law_term and law_term.strip()):
        return []
    terms_dir = Path(TERMS_DATA_DIR)
    if not terms_dir.exists():
        return []
    daily_terms = []
    for path in terms_dir.glob("lstrmRlt_*.json"):
        data = load_json(path)
        if not data or not isinstance(data, dict):
            continue
        items = extract_list_from_response(data, "lstrmRlt")
        for item in items:
            if not isinstance(item, dict):
                continue
            term = (
                item.get("법령용어") or item.get("법령용어명")
                or item.get("lawTerm") or item.get("용어")
            )
            if term and isinstance(term, str) and law_term in term:
                daily_term = (
                    item.get("일상용어") or item.get("일상용어명")
                    or item.get("dailyTerm") or item.get("한글용어")
                )
                if daily_term and isinstance(daily_term, str) and (daily_term := daily_term.strip()):
                    daily_terms.append(daily_term)
    return list(dict.fromkeys(daily_terms))


def get_related_laws_from_lsRlt_cache(law_name: str) -> List[str]:
    """
    api_data/related/ 의 lsRlt_*.json 캐시에서, 법령명에 대한 관련 법령 목록을 반환.
    """
    try:
        from config import RELATED_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    if not (law_name and law_name.strip()):
        return []
    related_dir = Path(RELATED_DATA_DIR)
    if not related_dir.exists():
        return []
    related_laws = []
    for path in related_dir.glob("lsRlt_*.json"):
        data = load_json(path)
        if not data or not isinstance(data, dict):
            continue
        items = extract_list_from_response(data, "lsRlt")
        for item in items:
            if not isinstance(item, dict):
                continue
            related_law = (
                item.get("법령명") or item.get("법령명_한글")
                or item.get("lawNm") or item.get("관련법령명")
            )
            if related_law and isinstance(related_law, str) and (related_law := related_law.strip()):
                related_laws.append(related_law)
    return list(dict.fromkeys(related_laws))


def get_articles_from_lstrmRltJo_cache(law_term: str) -> List[str]:
    """
    api_data/terms/ 의 lstrmRltJo_*.json 캐시에서, 법령용어에 연계된 조문 번호를 수집해 반환.
    """
    try:
        from config import TERMS_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    if not (law_term and law_term.strip()):
        return []
    terms_dir = Path(TERMS_DATA_DIR)
    if not terms_dir.exists():
        return []
    article_nums = []
    for path in terms_dir.glob("lstrmRltJo_*.json"):
        data = load_json(path)
        if not data or not isinstance(data, dict):
            continue
        items = extract_list_from_response(data, "lstrmRltJo")
        for item in items:
            if not isinstance(item, dict):
                continue
            term = (
                item.get("법령용어") or item.get("법령용어명")
                or item.get("lawTerm") or item.get("용어")
            )
            if term and isinstance(term, str) and law_term in term:
                jo_no = (
                    item.get("조문번호") or item.get("조문번호_한글")
                    or item.get("joNo") or item.get("JO")
                )
                if jo_no and isinstance(jo_no, str) and (jo_no := jo_no.strip()):
                    article_nums.append(jo_no)
    return list(dict.fromkeys(article_nums))


def get_law_terms_from_joRltLstrm_cache(article_num: str) -> List[str]:
    """
    api_data/related/ 의 joRltLstrm_*.json 캐시에서, 조문 번호에 연계된 법령용어를 수집해 반환.
    """
    try:
        from config import RELATED_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    if not (article_num and article_num.strip()):
        return []
    related_dir = Path(RELATED_DATA_DIR)
    if not related_dir.exists():
        return []
    law_terms = []
    for path in related_dir.glob("joRltLstrm_*.json"):
        data = load_json(path)
        if not data or not isinstance(data, dict):
            continue
        items = extract_list_from_response(data, "joRltLstrm")
        for item in items:
            if not isinstance(item, dict):
                continue
            jo_no = (
                item.get("조문번호") or item.get("조문번호_한글")
                or item.get("joNo") or item.get("JO")
            )
            if not jo_no or not isinstance(jo_no, str):
                continue
            jo_no = jo_no.strip()
            num_part = "".join(c for c in str(article_num) if c.isdigit()) or str(article_num)
            jo_part = "".join(c for c in jo_no if c.isdigit()).lstrip("0") or "0"
            match = article_num in jo_no or jo_no in article_num or (num_part and jo_part and num_part == jo_part)
            if not match:
                continue
                term = (
                    item.get("법령용어") or item.get("법령용어명")
                    or item.get("lawTerm") or item.get("용어")
                )
                if term and isinstance(term, str) and (term := term.strip()):
                    law_terms.append(term)
    return list(dict.fromkeys(law_terms))


def get_precedents_from_cache(keyword: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    api_data/precedents/ 캐시에서 판례 목록을 반환.
    """
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "prec" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    # 판례 목록 추출 (구조에 따라 다를 수 있음)
    precedents = []
    if isinstance(data.get("prec"), list):
        precedents = data["prec"][:max_results]
    elif isinstance(data.get("precService"), dict) and isinstance(data["precService"].get("prec"), list):
        precedents = data["precService"]["prec"][:max_results]
    return precedents


def get_nlrc_decisions_from_cache(keyword: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    api_data/precedents/ 캐시에서 노동위원회 결정례 목록을 반환.
    """
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "nlrc" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    decisions = []
    if isinstance(data.get("nlrc"), list):
        decisions = data["nlrc"][:max_results]
    elif isinstance(data.get("nlrcService"), dict) and isinstance(data["nlrcService"].get("nlrc"), list):
        decisions = data["nlrcService"]["nlrc"][:max_results]
    return decisions


def get_moel_explanations_from_cache(keyword: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    api_data/precedents/ 캐시에서 고용노동부 법령해석 목록을 반환.
    """
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "moelCgmExpc" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    explanations = []
    if isinstance(data.get("moelCgmExpc"), list):
        explanations = data["moelCgmExpc"][:max_results]
    elif isinstance(data.get("moelCgmExpcService"), dict) and isinstance(data["moelCgmExpcService"].get("moelCgmExpc"), list):
        explanations = data["moelCgmExpcService"]["moelCgmExpc"][:max_results]
    return explanations


def get_expc_from_cache(keyword: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """법령해석례 목록 반환."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "expc" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    results = []
    if isinstance(data.get("expc"), list):
        results = data["expc"][:max_results]
    elif isinstance(data.get("expcService"), dict) and isinstance(data["expcService"].get("expc"), list):
        results = data["expcService"]["expc"][:max_results]
    return results


def get_eiac_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """고용보험심사위원회 결정례 목록 반환."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "eiac" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    results = []
    if isinstance(data.get("eiac"), list):
        results = data["eiac"][:max_results]
    elif isinstance(data.get("eiacService"), dict) and isinstance(data["eiacService"].get("eiac"), list):
        results = data["eiacService"]["eiac"][:max_results]
    return results


def get_lstrmAI_from_cache(law_term: str) -> List[str]:
    """법령용어 조회 (lstrmAI) - 법령용어의 정의/설명 반환."""
    try:
        from config import TERMS_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    terms_dir = Path(TERMS_DATA_DIR)
    if not terms_dir.exists():
        return []
    path = terms_dir / "lstrmAI.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    items = extract_list_from_response(data, "lstrmAI")
    definitions = []
    for item in items:
        if not isinstance(item, dict):
            continue
        term = item.get("법령용어") or item.get("법령용어명") or item.get("lawTerm") or ""
        if term and isinstance(term, str) and law_term in term:
            definition = item.get("정의") or item.get("용어정의") or item.get("definition") or ""
            if definition and isinstance(definition, str):
                definitions.append(definition)
    return definitions[:3]  # 최대 3개


def get_dlytrm_from_cache(daily_term: str) -> List[str]:
    """일상용어 조회 (dlytrm) - 일상용어의 법령용어 대응 반환."""
    try:
        from config import TERMS_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    terms_dir = Path(TERMS_DATA_DIR)
    if not terms_dir.exists():
        return []
    path = terms_dir / "dlytrm.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    items = extract_list_from_response(data, "dlytrm")
    law_terms = []
    for item in items:
        if not isinstance(item, dict):
            continue
        daily = item.get("일상용어") or item.get("일상용어명") or item.get("dailyTerm") or ""
        if daily and isinstance(daily, str) and daily_term in daily:
            law_term = item.get("법령용어") or item.get("법령용어명") or item.get("lawTerm") or ""
            if law_term and isinstance(law_term, str):
                law_terms.append(law_term)
    return list(dict.fromkeys(law_terms))[:3]  # 최대 3개


def get_molegCgmExpc_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """법제처 법령해석 목록 반환."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "molegCgmExpc" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    results = []
    if isinstance(data.get("molegCgmExpc"), list):
        results = data["molegCgmExpc"][:max_results]
    elif isinstance(data.get("molegCgmExpcService"), dict) and isinstance(data["molegCgmExpcService"].get("molegCgmExpc"), list):
        results = data["molegCgmExpcService"]["molegCgmExpc"][:max_results]
    return results


def get_mojCgmExpc_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """법무부 법령해석 목록 반환."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "mojCgmExpc" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    results = []
    if isinstance(data.get("mojCgmExpc"), list):
        results = data["mojCgmExpc"][:max_results]
    elif isinstance(data.get("mojCgmExpcService"), dict) and isinstance(data["mojCgmExpcService"].get("mojCgmExpc"), list):
        results = data["mojCgmExpcService"]["mojCgmExpc"][:max_results]
    return results


def get_iaciac_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """산업재해보상보험재심사위원회 결정례 목록 반환."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    from rag.sync_common import load_json
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "iaciac" / "by_keyword" / f"{safe}.json"
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    results = []
    if isinstance(data.get("iaciac"), list):
        results = data["iaciac"][:max_results]
    elif isinstance(data.get("iaciacService"), dict) and isinstance(data["iaciacService"].get("iaciac"), list):
        results = data["iaciacService"]["iaciac"][:max_results]
    return results


def _get_precedent_list_from_file(path: Path, list_keys: tuple) -> List[Dict[str, Any]]:
    """저장된 JSON에서 여러 가능한 키 경로로 목록 추출 (detc/decc/ppc/ftc 등 API 응답 형태 다양)."""
    from rag.sync_common import load_json
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []
    for key in list_keys:
        val = data.get(key)
        if isinstance(val, dict):
            for sub in ("detc", "Detc", "decc", "ppc", "Ppc", "ftc", "Ftc"):
                if sub in val and isinstance(val[sub], list):
                    return val[sub]
        if isinstance(val, list):
            return val
    return []


def get_detc_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """헌법재판소 결정례 목록 반환 (DetcSearch.Detc)."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "detc" / "by_keyword" / f"{safe}.json"
    items = _get_precedent_list_from_file(path, ("DetcSearch", "detcSearch", "detc"))
    return items[:max_results] if isinstance(items, list) else []


def get_decc_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """행정심판 재결례 목록 반환 (Decc.decc)."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "decc" / "by_keyword" / f"{safe}.json"
    items = _get_precedent_list_from_file(path, ("Decc", "decc"))
    return items[:max_results] if isinstance(items, list) else []


def get_ppc_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """개인정보보호위원회 결정례 목록 반환 (Ppc.ppc 등)."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "ppc" / "by_keyword" / f"{safe}.json"
    items = _get_precedent_list_from_file(path, ("Ppc", "ppc"))
    return items[:max_results] if isinstance(items, list) else []


def get_ftc_from_cache(keyword: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """공정거래위원회 결정례 목록 반환 (Ftc.ftc 등)."""
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in keyword)
    path = precedents_dir / "ftc" / "by_keyword" / f"{safe}.json"
    items = _get_precedent_list_from_file(path, ("Ftc", "ftc"))
    return items[:max_results] if isinstance(items, list) else []
