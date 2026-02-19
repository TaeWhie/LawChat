# -*- coding: utf-8 -*-
"""벡터 스토어에 법률이 포함되어 있는지 확인"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.store import build_vector_store, search
from config import (
    SOURCE_MIN_WAGE_LAW,
    SOURCE_RETIREMENT_LAW,
    SOURCE_GENDER_EQUALITY_LAW,
    SOURCE_SAFETY_LAW,
    SOURCE_INDUSTRIAL_ACCIDENT_LAW,
    SOURCE_UNION_LAW,
)

collection, _ = build_vector_store()

laws_to_check = [
    ("최저임금법", SOURCE_MIN_WAGE_LAW, "제5조"),
    ("산업재해보상보험법", SOURCE_INDUSTRIAL_ACCIDENT_LAW, "제37조"),
    ("산업안전보건법", SOURCE_SAFETY_LAW, "제52조"),
    ("노동조합 및 노동관계조정법", SOURCE_UNION_LAW, "제81조"),
    ("남녀고용평등법", SOURCE_GENDER_EQUALITY_LAW, "제19조"),
]

print("="*80)
print("벡터 스토어 법률 포함 여부 확인")
print("="*80)

for law_name, source, article in laws_to_check:
    # 해당 법률 소스에서 검색
    results = search(collection, article, top_k=10, filter_sources=[source])
    print(f"\n{law_name} ({source}):")
    print(f"  조문 검색 결과: {len(results)}개")
    if results:
        for r in results[:3]:
            print(f"    - {r.get('source', '')} {r.get('article', '')}")
    else:
        print(f"  ⚠️ {article} 조문을 찾을 수 없습니다!")
