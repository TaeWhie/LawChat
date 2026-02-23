import json
from pathlib import Path

# Extract from ALL_LABOR_LAW_SOURCES (simulate config)
expected_name = "남녀고용평등과 일·가정 양립 지원에 관한 법률(법률)".split("(")[0].strip()

# Read from parsed file
with open("api_data/laws/law/276851.json", encoding="utf-8") as f:
    data = json.load(f)

# The parsing logic in api_chapters.py
parsed_name = data.get("기본정보", {}).get("법령명_한글", "")
if not parsed_name:
    # api_data_loader.py structure?
    for k, v in data.items():
        if isinstance(v, dict) and "법령명_한글" in v:
            parsed_name = v["법령명_한글"]
            break
        elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and "법령명_한글" in v[0]:
            parsed_name = v[0]["법령명_한글"]
            break

print("Expected   :", expected_name)
print("Parsed     :", parsed_name)

parsed_normalized = parsed_name.replace("ㆍ", "·")

print("Normalized :", parsed_normalized)
print("Match?     :", expected_name == parsed_normalized)

print("Expected bytes  :", expected_name.encode('utf-8'))
print("Parsed bytes    :", parsed_name.encode('utf-8'))
print("Normalized bytes:", parsed_normalized.encode('utf-8'))
