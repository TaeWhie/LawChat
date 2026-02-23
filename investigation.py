
import sys
from pathlib import Path
import json

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag.law_json import get_laws

def main():
    laws = get_laws()
    result = []
    for group in laws:
        group_info = {
            "group_name": group['group_name'],
            "items": [
                {"name": item['name'], "id": item['id'], "source": item['source']}
                for item in group['items']
            ]
        }
        result.append(group_info)
    
    with open("laws_debug.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"Total law groups: {len(laws)}")
    print("Results written to laws_debug.json")

if __name__ == "__main__":
    main()
