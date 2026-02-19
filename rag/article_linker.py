# -*- coding: utf-8 -*-
"""결론 텍스트에서 조항을 찾아 링크로 변환하는 유틸리티"""

import re
from typing import List, Tuple, Optional, Dict
from rag.store import build_vector_store, search_by_article_numbers
from config import SOURCE_LAW


def extract_article_citations(text: str) -> List[Tuple[str, str]]:
    """
    텍스트에서 조항 인용을 추출합니다.
    반환: [(법률명, 조항번호), ...]
    예: "근로기준법 제36조" -> [("근로기준법", "제36조")]
    """
    # 패턴: 법률명 + 제N조(또는 제N조의N)
    pattern = r"([가-힣]+법(?:률)?)\s*제(\d+(?:의\d+)?)조"
    matches = re.findall(pattern, text)
    
    citations = []
    seen = set()
    for law_name, article_num in matches:
        # "법률" 제거 (예: "근로기준법률" -> "근로기준법")
        law_name = law_name.replace("법률", "법")
        article_key = f"{law_name}:제{article_num}조"
        if article_key not in seen:
            citations.append((law_name, f"제{article_num}조"))
            seen.add(article_key)
    
    return citations


def find_article_info(law_name: str, article_number: str, collection) -> Optional[Dict]:
    """
    법률명과 조항 번호로 조항 정보를 찾습니다.
    반환: {law_id, article_number, source, chapter, ...} 또는 None
    """
    try:
        # 조항 번호로 검색
        results = search_by_article_numbers(collection, [article_number], SOURCE_LAW)
        
        # 법률명이 일치하는 결과 찾기
        for r in results:
            source = r.get("source", "")
            # source에서 법률명 추출 (예: "근로기준법(법률)" -> "근로기준법")
            source_law_name = source.replace("(법률)", "").replace("(시행령)", "").replace("(시행규칙)", "").strip()
            
            if law_name in source_law_name or source_law_name in law_name:
                return {
                    "law_id": r.get("law_id", ""),
                    "article_number": article_number,
                    "source": source,
                    "chapter": r.get("chapter", ""),
                }
        
        # 정확히 일치하지 않으면 첫 번째 결과 반환
        if results:
            return {
                "law_id": results[0].get("law_id", ""),
                "article_number": article_number,
                "source": results[0].get("source", ""),
                "chapter": results[0].get("chapter", ""),
            }
    except Exception:
        pass
    
    return None
