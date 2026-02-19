# -*- coding: utf-8 -*-
"""Inspect 근로기준법 JSON for chapter headers."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    law_dir = ROOT / "api_data" / "laws" / "law"
    for p in sorted(law_dir.glob("*.json")):
        if p.name == "list.json":
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key in ("법령", "law", "LawService"):
            v = d.get(key)
            if not isinstance(v, dict):
                continue
            info = v.get("기본정보") or v.get("basicInfo") or v
            name = (info.get("법령명_한글") or info.get("법령명한글") or "").strip()
            if not name or "근로기준법" not in name or "시행" in name:
                continue
            print("File:", p.name, "| Law:", name)
            jo = v.get("조문") or v.get("jo")
            if not isinstance(jo, dict):
                continue
            units = jo.get("조문단위") or jo.get("article") or []
            for i, u in enumerate(units):
                if not isinstance(u, dict):
                    continue
                content = u.get("조문내용") or u.get("joContent") or ""
                if isinstance(content, list):
                    content = " ".join(str(x) for x in content)
                content = str(content).strip()
                gubun = (u.get("조문여부") or "").strip()
                jo_no = u.get("조문번호") or u.get("joNo") or ""
                # Chapter header: 제N장 or 제N장의2 or 부칙
                if re.search(r"제\d+장|부칙", content) and len(content) < 120:
                    print(f"  [{gubun}] jo_no={jo_no} | {content[:70]}")
            return
    print("No 근로기준법 (without 시행) found.")

if __name__ == "__main__":
    main()
