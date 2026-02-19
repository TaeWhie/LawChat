# -*- coding: utf-8 -*-
"""최신 시나리오 테스트 결과 확인"""
import json
from pathlib import Path
from datetime import datetime

result_files = sorted(Path(".").glob("scenario_test_results_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

if not result_files:
    print("결과 파일이 없습니다.")
    exit(1)

latest_file = result_files[0]
print(f"최신 결과 파일: {latest_file.name}")
print(f"생성 시간: {datetime.fromtimestamp(latest_file.stat().st_mtime)}")
print("="*80)

with open(latest_file, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"\n평균 점수: {data['average_score']:.1f}/100")
print(f"총 시나리오: {data['total_scenarios']}개")
print(f"\n점수 분포:")
print(f"  100점: {sum(1 for r in data['results'] if r['score'] == 100)}개")
print(f"  80점 이상: {sum(1 for r in data['results'] if r['score'] >= 80)}개")
print(f"  60점 이상: {sum(1 for r in data['results'] if r['score'] >= 60)}개")
print(f"  60점 미만: {sum(1 for r in data['results'] if r['score'] < 60)}개")

print("\n시나리오별 상세 결과:")
for r in data['results']:
    score = r['score']
    status = "✅" if score == 100 else "⚠️" if score >= 80 else "❌"
    print(f"{status} [{r['scenario_id']}] {r['scenario_name']}: {score}/100점")
    if r.get('missing_articles'):
        print(f"    누락 조문: {r['missing_articles']}")
    if r.get('missing_laws'):
        print(f"    누락 법률: {r['missing_laws']}")
    if r.get('step2', {}).get('checklist_count', 0) == 0:
        print(f"    ⚠️ 체크리스트 생성 실패")
