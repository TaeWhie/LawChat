# -*- coding: utf-8 -*-
"""시나리오 테스트 결과 분석"""
import json
from pathlib import Path

result_file = Path("scenario_test_results_20260218_194018.json")
with open(result_file, "r", encoding="utf-8") as f:
    data = json.load(f)

print("="*80)
print("시나리오 테스트 결과 분석")
print("="*80)
print(f"\n평균 점수: {data['average_score']:.1f}/100")
print(f"총 시나리오: {data['total_scenarios']}개\n")

# 누락된 조문/법률 집계
missing_articles = {}
missing_laws = {}
low_scores = []

for r in data['results']:
    scenario_id = r['scenario_id']
    name = r['scenario_name']
    score = r['score']
    
    if score < 60:
        low_scores.append((scenario_id, name, score))
    
    for art in r.get('missing_articles', []):
        key = f"{scenario_id}. {name}: {art}"
        missing_articles[key] = missing_articles.get(key, 0) + 1
    
    for law in r.get('missing_laws', []):
        missing_laws[law] = missing_laws.get(law, 0) + 1

print("점수 낮은 시나리오:")
for sid, name, score in low_scores:
    print(f"  [{sid}] {name}: {score}/100점")

print("\n누락된 법률 (빈도순):")
for law, count in sorted(missing_laws.items(), key=lambda x: x[1], reverse=True):
    print(f"  - {law}: {count}회")

print("\n누락된 조문:")
for art_key in sorted(missing_articles.keys()):
    print(f"  - {art_key}")

print("\n" + "="*80)
print("주요 문제점:")
print("="*80)
print("1. 결론에 법률명이 포함되지 않음 (found_laws가 빈 경우 많음)")
print("2. 새로운 법률(최저임금법, 산재보험법 등)의 조문이 검색되지 않음")
print("3. 시나리오 10: 체크리스트 생성 실패 (0개)")
print("4. 이슈 분류가 잘못됨 (예: 시나리오 7, 8, 9, 10)")
