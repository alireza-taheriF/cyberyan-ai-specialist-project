#!/usr/bin/env python3
"""
Unit 3 & Unit 4 Verification Checks: Documentation (notes.md & README.md)
Failure State Names: ERR_U3_NOTES_INCOMPLETE, ERR_U4_README_INCOMPLETE
Exit Code 0 = PASS, Non-Zero = FAIL
"""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_MD = os.path.join(PROJECT_ROOT, "notes.md")
README_MD = os.path.join(PROJECT_ROOT, "README.md")


def check_notes():
    if not os.path.exists(NOTES_MD):
        return False, "notes.md does not exist", "Missing file"
    with open(NOTES_MD, "r", encoding="utf-8") as f:
        content = f.read()
    if len(content) < 3500:
        return False, "notes.md is shorter than 3500 characters", f"Length: {len(content)}"
    if len(content) > 9000:
        return False, "notes.md must stay short (the brief asks for a short file)", f"Length: {len(content)}"

    required_topics = [
        "User-Agent",
        "Rate Limiting",
        "Headers",
        "HTTP",
        "Redis",
        "Kafka",
        "Queue",
        "مقیاس بزرگ",
        "فرضیات",
        "Centrality",
        "TF-IDF"
    ]
    missing = [t for t in required_topics if t.lower() not in content.lower()]
    if missing:
        return False, "notes.md missing required technical topics", f"Missing: {missing}"
    return True, "OK", f"Length: {len(content)} chars"


def check_readme():
    if not os.path.exists(README_MD):
        return False, "README.md does not exist", "Missing file"
    with open(README_MD, "r", encoding="utf-8") as f:
        content = f.read()
    if len(content) < 2500:
        return False, "README.md is shorter than 2500 characters", f"Length: {len(content)}"

    required_sections = [
        "extractor.py",
        "analyzer.py",
        "profiles.json",
        "graph.png",
        "graph.json",
        "report.md",
        "notes.md",
        "نحوه اجرا",
        "منبع",
        "ساختگی"
    ]
    missing = [s for s in required_sections if s.lower() not in content.lower()]
    if missing:
        return False, "README.md missing required sections or file references", f"Missing: {missing}"
    return True, "OK", f"Length: {len(content)} chars"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("notes", "both"):
        ok, reason, ev = check_notes()
        if not ok:
            print(json.dumps({
                "UNIT": "unit_3_docs_notes",
                "VERDICT": "FAIL",
                "REASON": f"ERR_U3_NOTES_INCOMPLETE: {reason}",
                "EVIDENCE": ev,
                "SCOPE": "notes.md"
            }, ensure_ascii=False))
            sys.exit(1)
        if mode == "notes":
            print(json.dumps({"UNIT": "unit_3_docs_notes", "VERDICT": "PASS", "EVIDENCE": ev, "SCOPE": "notes.md"}))
            sys.exit(0)

    if mode in ("readme", "both"):
        ok, reason, ev = check_readme()
        if not ok:
            print(json.dumps({
                "UNIT": "unit_4_docs_readme",
                "VERDICT": "FAIL",
                "REASON": f"ERR_U4_README_INCOMPLETE: {reason}",
                "EVIDENCE": ev,
                "SCOPE": "README.md"
            }, ensure_ascii=False))
            sys.exit(1)
        if mode == "readme":
            print(json.dumps({"UNIT": "unit_4_docs_readme", "VERDICT": "PASS", "EVIDENCE": ev, "SCOPE": "README.md"}))
            sys.exit(0)

    print(json.dumps({"UNIT": "unit_3_and_4_docs", "VERDICT": "PASS"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
