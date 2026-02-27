import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "checklist_batch_multi_result.json")


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    summary = []
    for sc in data:
        rid = sc.get("id")
        situation = sc.get("situation")
        res = sc.get("result", {})
        classify = res.get("classify", {})
        issues = (classify.get("data") or {}).get("issues") or []
        issues = list(issues)
        item = {
            "id": rid,
            "situation": situation,
            "issues": issues,
            "issues_detail": [],
        }
        for cl in res.get("checklists", []):
            issue_name = cl.get("issue")
            rounds_info = []
            for r in cl.get("rounds", []):
                d = r.get("data") or {}
                rounds_info.append(
                    {
                        "round": r.get("round"),
                        "status_code": r.get("status_code"),
                        "should_continue": d.get("should_continue"),
                        "num_questions": len(d.get("checklist") or []),
                    }
                )
            item["issues_detail"].append(
                {
                    "issue": issue_name,
                    "rounds": rounds_info,
                }
            )
        summary.append(item)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
