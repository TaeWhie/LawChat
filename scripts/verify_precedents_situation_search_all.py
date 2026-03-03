# -*- coding: utf-8 -*-
"""
모든 이슈(PRIMARY_ISSUES)에 대해 상황·체크리스트 반영 판례 검색을 **API 호출**로 실행.
이슈 간 딜레이를 두어 연속 호출로 인한 봇 차단을 줄입니다.

사용법:
  python scripts/verify_precedents_situation_search_all.py
  python scripts/verify_precedents_situation_search_all.py --delay 6 --out result.txt
  python scripts/verify_precedents_situation_search_all.py --detail  # 각 판례 본문(판시사항·판결요지) 조회 후 출력
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _format_precedent_block(prec: Dict[str, Any], index: int, detail: Optional[Dict[str, Any]] = None) -> List[str]:
    """한 건 판례를 자세한 내용 포함해 텍스트 블록으로 반환."""
    lines = []
    title = prec.get("사건명") or prec.get("사건번호") or "(제목없음)"
    lines.append(f"    [{index}] 사건명: {title}")
    for key in ("사건번호", "선고일자", "법원명", "데이터출처명", "판례일련번호", "판결유형"):
        val = prec.get(key)
        if val is not None and str(val).strip():
            lines.append(f"        {key}: {val}")
    link = prec.get("판례상세링크")
    if link:
        lines.append(f"        판례상세링크: https://www.law.go.kr{link}" if not link.startswith("http") else f"        판례상세링크: {link}")
    if detail:
        ps = detail.get("판시사항") or detail.get("판결요지") or detail.get("요지")
        if ps:
            text = (ps[:1500] + "…") if len(ps) > 1500 else ps
            lines.append(f"        [판시사항/판결요지]\n        {text}")
        ref = detail.get("참조조문") or detail.get("참조법령")
        if ref:
            lines.append(f"        참조조문: {ref}")
    return lines


def _fetch_precedent_detail(prec_id: str) -> Optional[Dict[str, Any]]:
    """판례 본문 API로 판시사항·판결요지 등 추출."""
    try:
        from rag.law_api_client import get_body
        r = get_body("prec", id=prec_id)
        if not r.get("success") or not r.get("data"):
            return None
        data = r["data"]
        if not isinstance(data, dict):
            return None
        for key in ("prec", "Prec", "판례"):
            if key in data and isinstance(data[key], dict):
                return data[key]
        return data
    except Exception:
        return None


# 이슈별 샘플 상황 (API 검색 쿼리가 이슈만으로 안 나오도록)
SAMPLE_SITUATION_BY_ISSUE = {
    "임금": "월급을 3개월째 못 받았어요.",
    "퇴직금": "5년 근무 후 퇴사했는데 퇴직금을 안 줘요.",
    "해고/징계": "정리해고 통보받았는데 해고예고는 50일 전에 받았어요.",
    "근로계약": "기간제로 2년 일했는데 계약 갱신 안 해준다고 해요.",
    "휴일/휴가": "연차휴가 쓸 수 있는데 회사가 거절해요.",
    "근로시간": "주 52시간 넘게 야근 시키는데 가산수당을 안 줘요.",
    "직장 내 괴롭힘": "상사가 계속 폭언과 무리한 업무 지시를 해요.",
    "근로자 보호": "산재 인정 받았는데 회사가 보상에 응하지 않아요.",
    "산재": "업무 중 다쳤는데 산재 신청이 거절됐어요.",
    "산업안전": "작업장 위험한데 안전장비 없이 일하라고 해요.",
    "노조": "노조 가입했다고 불이익을 주려 해요.",
    "최저임금": "수습기간이라 최저임금보다 적게 받고 있어요.",
    "남녀고용평등": "육아휴직 복직 후 불리한 배치를 당했어요.",
    "육아휴직": "육아휴직 신청했는데 회사가 거절해요.",
    "고용보험": "실업급여 신청했는데 불인정됐어요.",
    "도급·용역대금": "프리랜서로 일했는데 대금을 안 줘요.",
}

# 이슈별 샘플 조문(참조조문 JO 검색용 - 결론에 나올 법률 조문 시뮬레이션)
SAMPLE_LAW_RESULTS_BY_ISSUE = {
    "임금": [{"source": "근로기준법(법률)", "article": "제36조"}],
    "퇴직금": [{"source": "근로기준법(법률)", "article": "제34조"}],
    "해고/징계": [{"source": "근로기준법(법률)", "article": "제27조"}],
    "근로계약": [{"source": "근로기준법(법률)", "article": "제14조"}],
    "휴일/휴가": [{"source": "근로기준법(법률)", "article": "제55조"}],
    "근로시간": [{"source": "근로기준법(법률)", "article": "제53조"}],
    "직장 내 괴롭힘": [{"source": "근로기준법(법률)", "article": "제4조"}],
    "근로자 보호": [{"source": "산업재해보상보험법(법률)", "article": "제36조"}],
    "산재": [{"source": "산업재해보상보험법(법률)", "article": "제37조"}],
    "산업안전": [{"source": "산업안전보건법(법률)", "article": "제5조"}],
    "노조": [{"source": "노동조합 및 노동관계조정법(법률)", "article": "제81조"}],
    "최저임금": [{"source": "최저임금법(법률)", "article": "제4조"}],
    "남녀고용평등": [{"source": "남녀고용평등과 일·가정 양립 지원에 관한 법률(법률)", "article": "제11조"}],
    "육아휴직": [{"source": "남녀고용평등과 일·가정 양립 지원에 관한 법률(법률)", "article": "제19조"}],
    "고용보험": [{"source": "고용보험법(법률)", "article": "제43조"}],
    "도급·용역대금": [{"source": "근로기준법(법률)", "article": "제36조"}],
}


def main():
    parser = argparse.ArgumentParser(description="전체 이슈에 대해 상황 반영 판례 API 검색 (이슈당 1회, 딜레이 포함)")
    parser.add_argument("--delay", type=float, default=6.0, help="이슈당 API 호출 전 대기 시간(초). 기본 6초.")
    parser.add_argument("--out", type=str, default="precedent_verify_all_issues_api.txt", help="결과 저장 파일 (UTF-8)")
    parser.add_argument("--detail", action="store_true", help="각 판례 본문 API 조회 후 판시사항 판결요지 출력")
    args = parser.parse_args()

    from rag.labor_keywords import PRIMARY_ISSUES
    from rag.api_data_loader import get_precedents_for_conclusion, _build_precedent_search_query

    issues = list(PRIMARY_ISSUES)
    lines = []
    lines.append("=" * 70 + "\n")
    lines.append("전체 이슈 상황 반영 판례 검색 (API 호출)\n")
    lines.append("=" * 70 + "\n")
    lines.append(f"이슈 수: {len(issues)}, 호출 간 대기: {args.delay}초\n\n")

    print("=" * 70)
    print("전체 이슈 상황 반영 판례 검색 (API 호출)")
    print("=" * 70)
    print(f"이슈 수: {len(issues)}, 호출 간 대기: {args.delay}초\n")

    for i, issue in enumerate(issues):
        situation = SAMPLE_SITUATION_BY_ISSUE.get(issue, f"{issue} 관련 상담 문의입니다.")
        qa_text = f"Q: 해당 사안 관련해 확인할 게 있나요?\nA: 네 확인했습니다."
        query = _build_precedent_search_query(issue, situation=situation, qa_text=qa_text)

        if i > 0:
            print(f"[대기 {args.delay}초 후 다음 이슈 호출...]")
            time.sleep(args.delay)

        precs, meta = get_precedents_for_conclusion(
            issue, situation=situation, qa_text=qa_text,
            law_results=SAMPLE_LAW_RESULTS_BY_ISSUE.get(issue),
            max_results=5,
        )
        source = meta.get("source", "")
        query_used = meta.get("query_used", "")
        jo_used = meta.get("jo_used", "")
        count = meta.get("count", 0)
        titles = meta.get("titles", [])

        block = [
            f"[이슈] {issue}",
            f"  상황 샘플: {situation[:50]}{'…' if len(situation) > 50 else ''}",
            f"  검색 쿼리: {query_used or query!r}",
            f"  참조조문(JO): {jo_used or '(미사용)'}",
            f"  source: {source}",
            f"  로딩 건수: {count}건",
        ]
        if meta.get("api_error"):
            block.append(f"  ※ API 실패 사유: {meta.get('api_error')}")
        block.append("  판례 목록 (자세한 내용):")
        for j, prec in enumerate(precs or [], 1):
            detail = None
            if getattr(args, "detail", False):
                pid = prec.get("판례일련번호") or prec.get("id") or prec.get("ID")
                if pid:
                    time.sleep(2.0)
                    detail = _fetch_precedent_detail(str(pid))
            block.extend(_format_precedent_block(prec, j, detail))
        block.append("")

        text_block = "\n".join(block)
        lines.append(text_block + "\n")
        print(text_block)

    lines.append("=" * 70 + "\n")
    lines.append("검증 완료.\n")
    lines.append("=" * 70 + "\n")

    out_path = Path(args.out)
    out_path.write_text("\n".join(lines).replace("\n\n\n", "\n\n"), encoding="utf-8")
    print("=" * 70)
    print(f"결과 저장: {out_path.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
