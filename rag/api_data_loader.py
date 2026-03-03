# -*- coding: utf-8 -*-
"""
api_data/ 에 저장된 API 응답을 RAG용 청크로 로드.

- 법령/행정규칙 본문: api_data/laws/law/*.json, laws/admrul/*.json
- 저장 형식은 law_api_client.get_body() 응답 그대로 (국가법령정보 API JSON 구조)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _build_precedent_search_query(
    issue: str,
    situation: Optional[str] = None,
    qa_text: Optional[str] = None,
    max_query_len: int = 80,
) -> str:
    """
    결론용 판례 검색 쿼리 생성: 이슈 + 상황 요약 + 체크리스트 답변에서 추출한 핵심어.
    API 검색어 길이 제한을 고려해 max_query_len 이내로 자른다.
    """
    parts = [(issue or "").strip()]
    # 상황 문장 앞부분 (숫자·기간·해고/퇴직 등이 자주 나옴)
    if situation and situation.strip():
        s_clean = re.sub(r"\s+", " ", situation.strip())[:50]
        if s_clean and s_clean not in parts:
            parts.append(s_clean)
    # 체크리스트 답변에서 '네/아니요'가 아닌 구체적 답만 추출
    if qa_text and qa_text.strip():
        skip = {"네", "아니요", "(미입력)", "미입력", "q:", "a:", ""}
        answers = []
        for line in qa_text.splitlines():
            line = line.strip()
            if line.upper().startswith("A:") or line.startswith("A:"):
                ans = line[1:].strip().lstrip(":").strip()
                if ans and ans.lower() not in skip and len(ans) >= 2:
                    # 단어 단위로 (2글자 이상, 숫자+단위 허용)
                    for w in re.findall(r"[가-힣a-zA-Z0-9]+", ans):
                        if len(w) >= 2 and w not in skip and w not in answers:
                            answers.append(w)
                            if len(answers) >= 5:
                                break
            if len(answers) >= 5:
                break
        if answers:
            parts.append(" ".join(answers[:4]))
    query = " ".join(p for p in parts if p).strip()
    if len(query) > max_query_len:
        query = query[: max_query_len - 3].rstrip() + "..."
    return query


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """두 벡터의 코사인 유사도."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def rank_precedents_by_situation(
    precedents: List[Dict[str, Any]],
    situation: Optional[str] = None,
    qa_text: Optional[str] = None,
    issue: Optional[str] = None,
    top_k: int = 5,
    openai_api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    판례 목록을 사용자 상황과의 임베딩 유사도 순으로 정렬해 상위 top_k개 반환.
    situation/qa_text가 없으면 원래 순서대로 상위 top_k 반환.
    """
    if not precedents:
        return []
    situation_str = (situation or "").strip()
    if qa_text and qa_text.strip():
        qa_short = qa_text.replace("[User's initial situation]", "").strip()[:300]
        situation_str = (situation_str + " " + qa_short).strip()
    if not situation_str and not issue:
        return precedents[:top_k]
    try:
        from rag.store import get_embedding, get_embeddings_batch
    except ImportError:
        return precedents[:top_k]
    query_parts = [situation_str]
    if issue and issue.strip():
        query_parts.append(issue.strip())
    query_text = " ".join(query_parts).strip() or situation_str
    if not query_text:
        return precedents[:top_k]
    try:
        query_emb = list(get_embedding(query_text, api_key=openai_api_key))
    except Exception:
        return precedents[:top_k]
    prec_texts = []
    for p in precedents:
        if not isinstance(p, dict):
            prec_texts.append("")
            continue
        title = (p.get("사건명") or p.get("사건번호") or "").strip()
        summary = (p.get("판시사항") or p.get("요지") or p.get("판결요지") or "").strip()
        prec_texts.append(f"{title} {summary[:500]}" if summary else (title or "(제목없음)"))
    if not prec_texts:
        return precedents[:top_k]
    try:
        prec_embs = get_embeddings_batch(prec_texts, api_key=openai_api_key)
    except Exception:
        return precedents[:top_k]
    scored = [( _cosine_similarity(query_emb, emb), i, prec) for i, (prec, emb) in enumerate(zip(precedents, prec_embs))]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [x[2] for x in scored[:top_k]]


def _supplement_precedents_to_min(current: List[Dict[str, Any]], issue: str, min_count: int, seen_ids: set) -> List[Dict[str, Any]]:
    """current가 min_count 미만이면 캐시에서 중복 제외하고 추가해 min_count까지 채움."""
    if len(current) >= min_count:
        return current
    supplemental = get_precedents_from_cache(issue, max_results=min_count + 5)
    for p in supplemental:
        if len(current) >= min_count:
            break
        if not isinstance(p, dict):
            continue
        pid = p.get("판례일련번호") or p.get("id") or p.get("ID")
        pid_str = str(pid) if pid is not None else ""
        if pid_str and pid_str not in seen_ids:
            seen_ids.add(pid_str)
            current.append(p)
    return current


def _dedupe_precedents_by_id(prec_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """판례일련번호/id 기준 중복 제거, 순서 유지."""
    seen = set()
    out = []
    for p in prec_list:
        if not isinstance(p, dict):
            continue
        pid = p.get("판례일련번호") or p.get("id") or p.get("ID")
        pid_str = str(pid).strip() if pid is not None else ""
        if not pid_str:
            out.append(p)
            continue
        if pid_str in seen:
            continue
        seen.add(pid_str)
        out.append(p)
    return out


def get_precedents_for_conclusion(
    issue: str,
    situation: Optional[str] = None,
    qa_text: Optional[str] = None,
    law_results: Optional[List[Dict[str, Any]]] = None,
    max_results: int = 5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    결론 단계용 판례 조회.
    1) 결론에 쓰인 조문(law_results)이 있으면 참조조문(JO)으로 API 검색 우선 시도
    2) 이슈/상황 쿼리로 API 검색 시도
    3) 실패 시 이슈 키워드 캐시로 폴백.
    반환: (precedents_list, meta_dict)
    meta에 source="api" | "cache", query_used 또는 jo_used 포함.
    """
    meta: Dict[str, Any] = {
        "source": "cache",
        "keyword_used": issue,
        "path_used": "",
        "count": 0,
        "titles": [],
        "precedent_ids": [],
        "query_used": "",
        "jo_used": "",
    }
    query = _build_precedent_search_query(issue, situation, qa_text)
    has_situation = bool((situation or "").strip() or (qa_text or "").replace("[User's initial situation]", "").strip())
    INITIAL_FETCH = 15  # 1차 검색으로 더 가져온 뒤 상황 유사도로 상위 N건 선별

    def _fill_meta_from_prec_list(prec_list: list, try_label: str, use_jo: bool = False) -> bool:
        if not isinstance(prec_list, list) or not prec_list:
            return False
        prec_list = prec_list[:max_results]
        titles = []
        ids = []
        for p in prec_list:
            if isinstance(p, dict):
                titles.append(p.get("사건명") or p.get("사건번호") or "(제목없음)")
                pid = p.get("판례일련번호") or p.get("id") or p.get("ID")
                if pid is not None:
                    ids.append(str(pid))
        meta["source"] = "api"
        meta["query_used"] = try_label if not use_jo else ""
        meta["jo_used"] = try_label if use_jo else ""
        meta["count"] = len(prec_list)
        meta["titles"] = titles
        meta["precedent_ids"] = ids
        meta["keyword_used"] = try_label
        return True

    # 1) 결론에 나온 조문으로 참조조문(JO) 검색 우선 시도
    if law_results:
        try:
            from rag.law_api_client import search_list
            from rag.sync_common import extract_list_from_response
            refs = []
            for r in law_results[:5]:
                src = (r.get("source") or "").replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
                art = (r.get("article") or "").strip()
                if not art or not src:
                    continue
                m = re.match(r"(제\d+(?:의\d+)?조)", art)
                num = m.group(1) if m else None
                if num:
                    law_name = (src.split()[0] if src else "근로기준법").strip()
                    refs.append(f"{law_name} {num}")
            seen_ref = set()
            refs_unique = [x for x in refs if x not in seen_ref and not seen_ref.add(x)]
            merged = []
            seen_id = set()
            jo_labels = []
            for ref in refs_unique[:3]:
                r = search_list("prec", jo=ref, display=INITIAL_FETCH, page=1)
                if not r.get("success") or not r.get("data"):
                    continue
                data = r["data"]
                prec_list = extract_list_from_response(data, "prec")
                if not isinstance(prec_list, list):
                    continue
                jo_labels.append(ref)
                for p in prec_list:
                    if not isinstance(p, dict):
                        continue
                    pid = p.get("판례일련번호") or p.get("id") or p.get("ID")
                    pid_str = str(pid) if pid is not None else ""
                    if pid_str and pid_str not in seen_id:
                        seen_id.add(pid_str)
                        merged.append(p)
            if merged:
                if has_situation and len(merged) > max_results:
                    try:
                        from rag.context import openai_api_key_ctx
                        merged = rank_precedents_by_situation(
                            merged, situation=situation, qa_text=qa_text, issue=issue,
                            top_k=max_results, openai_api_key=openai_api_key_ctx.get(),
                        )
                    except Exception:
                        merged = merged[:max_results]
                else:
                    merged = merged[:max_results]
                if len(merged) < max_results:
                    merged = _supplement_precedents_to_min(merged, issue, max_results, seen_id)
                merged = _dedupe_precedents_by_id(merged)[:max_results]
                if _fill_meta_from_prec_list(merged, jo_labels[0] if jo_labels else "", use_jo=True):
                    if jo_labels:
                        meta["jo_used"] = ", ".join(jo_labels[:2])
                    return merged, meta
        except Exception as e:
            meta["error"] = str(e)
            meta["api_error"] = str(e)

    # 2) 상황/체크리스트가 있으면 API로 쿼리 검색 시도
    if has_situation and query and query != (issue or "").strip():
        try:
            from rag.law_api_client import search_list
            from rag.sync_common import extract_list_from_response
            # API는 다단어 쿼리에서 prec 키를 비울 수 있음 → 짧은 쿼리 시도 후, 실패 시 이슈만 재시도
            situation_part = ""
            if situation and situation.strip():
                words = re.findall(r"[가-힣a-zA-Z0-9]+", situation.strip())
                situation_part = " ".join(w for w in words[:3] if len(w) >= 2)[:15]
            api_query = ((issue or "").strip() + " " + situation_part).strip()[:22]
            if not api_query:
                api_query = (issue or "").strip()
            for attempt, try_query in enumerate([api_query, (issue or "").strip()]):
                if attempt > 0 and try_query == api_query:
                    continue
                # 이슈가 "해고/징계" 형태면 API는 단일 키워드가 나음 → 2차 시도 시 캐시용 키워드 사용
                if attempt > 0 and "/" in (issue or ""):
                    try:
                        cands = _precedent_keyword_candidates(issue)
                        try_query = next((c for c in cands if "/" not in c), try_query)
                    except Exception:
                        pass
                r = search_list("prec", query=try_query, display=INITIAL_FETCH, page=1)
                if not r.get("success") or not r.get("data"):
                    continue
                data = r["data"]
                prec_list = extract_list_from_response(data, "prec")
                if not isinstance(prec_list, list) or not prec_list:
                    continue
                if has_situation and len(prec_list) > max_results:
                    try:
                        from rag.context import openai_api_key_ctx
                        prec_list = rank_precedents_by_situation(
                            prec_list, situation=situation, qa_text=qa_text, issue=issue,
                            top_k=max_results, openai_api_key=openai_api_key_ctx.get(),
                        )
                    except Exception:
                        prec_list = prec_list[:max_results]
                else:
                    prec_list = prec_list[:max_results]
                seen_id = {str(p.get("판례일련번호") or p.get("id") or p.get("ID")) for p in prec_list if isinstance(p, dict)}
                if len(prec_list) < max_results:
                    prec_list = _supplement_precedents_to_min(prec_list, issue, max_results, seen_id)
                prec_list = _dedupe_precedents_by_id(prec_list)[:max_results]
                if _fill_meta_from_prec_list(prec_list, try_query, use_jo=False):
                    return prec_list, meta
            meta["api_error"] = "response_prec_empty_or_invalid"
        except Exception as e:
            meta["error"] = str(e)
            meta["api_error"] = str(e)
            meta["source"] = "cache_fallback"

    # 폴백: 이슈 키워드 캐시
    prec_list, cache_meta = get_precedents_from_cache_with_meta(issue, max_results)
    cache_meta["source"] = "cache"
    cache_meta["query_used"] = meta.get("query_used", "")
    cache_meta["jo_used"] = meta.get("jo_used", "")
    if meta.get("api_error"):
        cache_meta["api_error"] = meta["api_error"]
    if meta.get("error"):
        cache_meta["api_error"] = cache_meta.get("api_error") or meta["error"]
    return prec_list, cache_meta


def get_precedents_from_cache(keyword: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    api_data/precedents/ 캐시에서 판례 목록을 반환.
    이슈(primary)가 "해고/징계" 등이면 동기화 키워드(해고, 부당해고 등)로 후보를 시도.
    """
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return []
    from rag.sync_common import load_json, extract_list_from_response
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    if not precedents_dir.exists():
        return []
    # 이슈 문자열 → 캐시 파일명 후보 (동기화는 TERM_SYNC_KEYWORDS 기준으로만 저장됨)
    candidates = _precedent_keyword_candidates(keyword)
    for kw in candidates:
        safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in kw)
        path = precedents_dir / "prec" / "by_keyword" / f"{safe}.json"
        data = load_json(path)
        if not data or not isinstance(data, dict):
            continue
        prec_list = extract_list_from_response(data, "prec")
        if isinstance(prec_list, list) and prec_list:
            return prec_list[:max_results]
        # 레거시 구조 직접 확인
        if isinstance(data.get("prec"), list):
            return data["prec"][:max_results]
        if isinstance(data.get("precService"), dict) and isinstance(data["precService"].get("prec"), list):
            return data["precService"]["prec"][:max_results]
    return []


def _precedent_keyword_candidates(issue_or_keyword: str) -> List[str]:
    """
    결론 단계에서 쓰는 이슈(primary) → 판례 캐시 조회에 쓸 키워드 후보 목록.
    첫 번째는 원문 그대로 safe한 형태, 이후는 해당 이슈와 관련된 동기화 키워드.
    """
    s = (issue_or_keyword or "").strip()
    if not s:
        return []
    try:
        from rag.labor_keywords import PRIMARY_ISSUES, TERM_SYNC_KEYWORDS
    except ImportError:
        return [s]
    # primary 이슈 → 캐시에 있는 키워드 후보 (TERM_SYNC_KEYWORDS 기준)
    primary_to_sync = {
        "해고/징계": ["해고", "부당해고", "정리해고"],
        "휴일/휴가": ["연차휴가", "연차", "주휴일"],
        "도급·용역대금": [],  # 동기화 키워드 없음
        "근로자 보호": ["산재", "산업재해"],
        "노조": ["노동조합"],
    }
    out = [s]
    if s in primary_to_sync:
        out.extend(primary_to_sync[s])
    # 중복 제거 순서 유지
    seen = set()
    result = []
    for x in out:
        key = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in x)
        if key not in seen:
            seen.add(key)
            result.append(x)
    return result


def get_precedents_from_cache_with_meta(keyword: str, max_results: int = 5) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    판례 목록과 함께 '어떤 키워드로 어떤 파일에서 몇 건을 불러왔는지' 검증용 메타를 반환.
    반환: (precedents_list, meta_dict)
    meta_dict: keyword_used, path_used, count, titles, precedent_ids
    """
    try:
        from config import PRECEDENTS_DATA_DIR
    except ImportError:
        return [], {"keyword_used": keyword, "path_used": "", "count": 0, "titles": [], "precedent_ids": [], "error": "no_config"}
    from rag.sync_common import load_json, extract_list_from_response
    precedents_dir = Path(PRECEDENTS_DATA_DIR)
    meta = {"keyword_used": keyword, "path_used": "", "count": 0, "titles": [], "precedent_ids": []}
    if not precedents_dir.exists():
        return [], {**meta, "error": "precedents_dir_not_found"}
    candidates = _precedent_keyword_candidates(keyword)
    for kw in candidates:
        safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in kw)
        path = precedents_dir / "prec" / "by_keyword" / f"{safe}.json"
        data = load_json(path)
        if not data or not isinstance(data, dict):
            continue
        prec_list = extract_list_from_response(data, "prec")
        if not isinstance(prec_list, list):
            if isinstance(data.get("prec"), list):
                prec_list = data["prec"]
            elif isinstance(data.get("precService"), dict) and isinstance(data["precService"].get("prec"), list):
                prec_list = data["precService"]["prec"]
            else:
                continue
        prec_list = prec_list[:max_results]
        titles = []
        ids = []
        for p in prec_list:
            if isinstance(p, dict):
                titles.append(p.get("사건명") or p.get("사건번호") or "(제목없음)")
                pid = p.get("판례일련번호") or p.get("id") or p.get("ID")
                if pid is not None:
                    ids.append(str(pid))
        meta["keyword_used"] = kw
        meta["path_used"] = str(path)
        meta["count"] = len(prec_list)
        meta["titles"] = titles
        meta["precedent_ids"] = ids
        return prec_list, meta
    return [], meta


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
