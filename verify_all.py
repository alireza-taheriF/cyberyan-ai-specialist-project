#!/usr/bin/env python3
"""
Runs every check and validates the ZIP built by `src/merge_and_verify.py`.
Exit code 0 means all checks passed.
"""
import json
import os
import subprocess
import sys
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FINAL_ZIP = os.path.join(PROJECT_ROOT, "dist", "cyberyan_ai_specialist_project.zip")

REQUIRED_ZIP_ENTRIES = {
    "run.py",
    "start.sh",
    "browser_extension/manifest.json",
    "browser_extension/background.js",
    "src/extractor.py",
    "src/live_browser.py",
    "src/capture_server.py",
    "tests/test_capture.py",
    "tests/test_real_data.py",
    "urls.txt",
    "src/analyzer.py",
    "src/graph_analysis.py",
    "src/clustering.py",
    "src/reporting.py",
    "src/merge_and_verify.py",
    "data/profiles.json",
    "data/profiles_summary.csv",
    "data/activities_df.csv",
    "output/graph.json",
    "output/graph.png",
    "output/report.md",
    "README.md",
    "notes.md",
    "requirements.txt",
    "sample_data/synthetic_profiles.json",
    "verify_all.py",
    "tests/test_unit_1.py",
    "tests/test_unit_2.py",
    "tests/test_docs.py",
}


def run_check(cmd):
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    return res.returncode == 0, res.stdout.strip(), res.stderr.strip()


def main():
    steps = [
        ("unit_1_extractor", [sys.executable, "tests/test_unit_1.py"]),
        ("unit_2_analyzer", [sys.executable, "tests/test_unit_2.py"]),
        ("capture_server", [sys.executable, "tests/test_capture.py"]),
        ("real_data", [sys.executable, "tests/test_real_data.py"]),
        ("unit_3_docs_notes", [sys.executable, "tests/test_docs.py", "notes"]),
        ("unit_4_docs_readme", [sys.executable, "tests/test_docs.py", "readme"]),
    ]

    results = {}
    for unit_name, cmd in steps:
        ok, out, err = run_check(cmd)
        results[unit_name] = {"passed": ok, "stdout": out, "stderr": err}
        if not ok:
            print(json.dumps({
                "GLOBAL_VERDICT": "FAIL",
                "FAILED_UNIT": unit_name,
                "DETAILS": out or err
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

    if not os.path.exists(FINAL_ZIP):
        print(json.dumps({
            "GLOBAL_VERDICT": "FAIL",
            "FAILED_UNIT": "unit_5_merge_package",
            "REASON": "Missing ZIP archive; run src/merge_and_verify.py first",
            "EVIDENCE": FINAL_ZIP
        }, indent=2))
        sys.exit(1)

    with zipfile.ZipFile(FINAL_ZIP, "r") as zf:
        bad_file = zf.testzip()
        if bad_file is not None:
            print(json.dumps({
                "GLOBAL_VERDICT": "FAIL",
                "FAILED_UNIT": "unit_5_merge_package",
                "REASON": "Corrupted file inside ZIP archive",
                "EVIDENCE": bad_file
            }, indent=2))
            sys.exit(1)
        names = set(zf.namelist())
        missing = REQUIRED_ZIP_ENTRIES - names
        if missing:
            print(json.dumps({
                "GLOBAL_VERDICT": "FAIL",
                "FAILED_UNIT": "unit_5_merge_package",
                "REASON": "Missing required files in ZIP archive",
                "EVIDENCE": sorted(missing)
            }, indent=2))
            sys.exit(1)

        stale = []
        for name in sorted(REQUIRED_ZIP_ENTRIES):
            with open(os.path.join(PROJECT_ROOT, name), "rb") as f:
                if f.read() != zf.read(name):
                    stale.append(name)
        if stale:
            print(json.dumps({
                "GLOBAL_VERDICT": "FAIL",
                "FAILED_UNIT": "unit_5_merge_package",
                "REASON": "ZIP is older than the project files; rerun src/merge_and_verify.py",
                "EVIDENCE": stale
            }, indent=2))
            sys.exit(1)

    print(json.dumps({
        "GLOBAL_VERDICT": "PASS",
        "ALL_UNITS_PASSED": True,
        "ZIP_ARCHIVE": FINAL_ZIP,
        "ZIP_ENTRIES_COUNT": len(names),
        "UNIT_RESULTS": results
    }, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
