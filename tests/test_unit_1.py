#!/usr/bin/env python3
"""
Unit 1 check: page parser and extracted data (data/profiles.json and the two CSV DataFrames).
Exit Code 0 = PASS, Non-Zero = FAIL
"""
import json
import os
import sys
import tempfile
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import live_browser  # noqa: E402
from extractor import SOURCE_LIVE, SOURCE_SAMPLE  # noqa: E402

PROFILES_JSON = os.path.join(PROJECT_ROOT, "data", "profiles.json")
PROFILES_CSV = os.path.join(PROJECT_ROOT, "data", "profiles_summary.csv")
ACTIVITIES_CSV = os.path.join(PROJECT_ROOT, "data", "activities_df.csv")
EXTRACTOR_PY = os.path.join(PROJECT_ROOT, "src", "extractor.py")

REQUIRED_TOP_KEYS = {
    "profile_id", "public_identifier", "full_name", "headline",
    "current_company", "current_role", "department", "seniority",
    "location", "about", "connections_count", "followers_count",
    "experiences", "educations", "skills", "interests", "activities"
}

REQUIRED_EXP_KEYS = {"title", "company", "start_date", "end_date", "duration_months", "location", "description"}
REQUIRED_EDU_KEYS = {"school", "degree", "field_of_study", "start_year", "end_year"}
REQUIRED_INT_KEYS = {"name", "category", "type"}
REQUIRED_ACT_KEYS = {"activity_id", "type", "content", "timestamp", "likes_count", "comments_count", "interacted_with", "hashtags"}


def fail(reason: str, evidence: str):
    print(json.dumps({
        "UNIT": "unit_1_extractor",
        "VERDICT": "FAIL",
        "REASON": f"ERR_U1_SCHEMA_OR_COUNT: {reason}",
        "EVIDENCE": evidence,
        "SCOPE": "src/extractor.py, data/profiles.json, data/profiles_summary.csv"
    }, ensure_ascii=False))
    sys.exit(1)


def verify_no_invented_values():
    """A page that shows only a name must give nulls and empty lists, not defaults."""
    minimal = live_browser.parse_profile({"profile": "<main><div><h2>Only Name</h2></div></main>"}, "only-name", "p01")
    for field in ("headline", "location", "connections_count", "followers_count", "department",
                  "seniority", "current_company", "about"):
        if minimal[field] is not None:
            fail(f"Parser invented a value for missing field '{field}'", repr(minimal[field]))
    interests = live_browser.parse_interests(live_browser._root(
        '<main><div><h2>Interests</h2><label>Top Voices</label>'
        '<div componentkey="x"><a href="https://www.linkedin.com/in/some-voice/">Some Voice</a><p>· 2nd</p></div></div></main>'))
    if interests != [{"name": "Some Voice", "category": "Top Voice", "type": "following"}]:
        fail("Followed people (Top Voices) not parsed", str(interests))


def verify_browser_parsing():
    """Checks URL cleanup and the logged-in page parser against tests/fixtures (hand-written markup)."""
    url = live_browser.normalize_profile_url("3- https://www.linkedin.com/in/a-b/?lipi=urn%3Ali%3Apage")
    if url != "https://www.linkedin.com/in/a-b/":
        fail("URL normalization failed", str(url))

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("1- https://x.com/in/a/?q=1\n\n# note https://x.com/in/skip/\n2- https://x.com/in/a\nhttps://x.com/in/b/\n")
    parsed_urls = live_browser.read_urls_file(f.name)
    os.unlink(f.name)
    if parsed_urls != ["https://x.com/in/a/", "https://x.com/in/b/"]:
        fail("URL file parsing failed", str(parsed_urls))

    fixtures = os.path.join(PROJECT_ROOT, "tests", "fixtures")
    urls = ["https://www.linkedin.com/in/jane-fixture/", "https://www.linkedin.com/in/omid-fixture/"]
    jane, omid = live_browser.parse_capture_dir(urls, fixtures)
    exp = jane["experiences"]
    checks = {
        "name": jane["full_name"] == "Jane Fixture",
        "headline": jane["headline"] == "ML Engineer at Acme",
        "location": jane["location"] == "Berlin, Germany",
        "connections": jane["connections_count"] == 500,
        "followers": jane["followers_count"] == 1234,
        "about": jane["about"] == "Builds ranking models.",
        "single role": (exp[0]["title"], exp[0]["company"], exp[0]["duration_months"], exp[0]["location"]) == ("ML Engineer", "Acme", 27, "Berlin"),
        "description kept out of fields": exp[0]["description"] == "Ranking and retrieval.",
        "grouped roles": [(e["title"], e["company"]) for e in exp[1:]] == [("Lead", "Beta"), ("Engineer", "Beta")],
        "description is not a location": exp[1]["location"] == "Israel",
        "education from details page": [(e["school"], e["degree"]) for e in jane["educations"]] == [("Sharif University", "MSc"), ("Tehran University", "BSc"), ("Allameh Helli", "Diploma")],
        "skills from details page": jane["skills"] == ["PyTorch", "Python", "Graph Neural Networks"],
        "interests": jane["interests"] == [{"name": "OpenAI", "category": "Company", "type": "following"}],
        "activity types": [a["type"] for a in jane["activities"]] == ["post", "repost"],
        "activity time": jane["activities"][0]["timestamp"].startswith("20"),
        "activity link": jane["activities"][0]["interacted_with"] == ["p02"],
        "reactions": jane["activities"][0]["likes_count"] == 12,
        "hashtags": jane["activities"][0]["hashtags"] == ["#ml"],
        "missing section": omid["missing_sections"] == ["experiences", "educations", "skills", "interests", "activities"],
        "live label": jane["data_source"] == SOURCE_LIVE,
    }
    checks["percent-encoded slug"] = live_browser.slug_of("https://x.com/in/%D8%B9%D9%84%DB%8C/") == "علی"
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        fail("Browser page parser failed", str(failed))


def main():
    for path in [EXTRACTOR_PY, PROFILES_JSON, PROFILES_CSV, ACTIVITIES_CSV]:
        if not os.path.exists(path):
            fail("Missing required file", f"File not found: {path}")

    # Verify live HTTP client & Voyager JSON parser
    verify_no_invented_values()
    verify_browser_parsing()

    with open(PROFILES_JSON, "r", encoding="utf-8") as f:
        try:
            profiles = json.load(f)
        except Exception as e:
            fail("Invalid JSON in profiles.json", str(e))

    if not isinstance(profiles, list) or not profiles:
        fail("profiles.json must be a non-empty list", str(type(profiles)))
    if profiles[0].get("data_source") == SOURCE_SAMPLE and len(profiles) != 10:
        fail("The bundled sample must have exactly 10 profiles", f"Found {len(profiles)}")

    seen_ids = set()
    valid_ids = {p.get("profile_id") for p in profiles if isinstance(p, dict)}

    for idx, p in enumerate(profiles):
        missing = REQUIRED_TOP_KEYS - set(p.keys())
        if missing:
            fail(f"Profile {idx} missing keys", f"Missing: {sorted(missing)}")

        pid = p["profile_id"]
        if p.get("data_source") not in (SOURCE_LIVE, SOURCE_SAMPLE):
            fail("Profile has no valid data_source label", f"{pid}: {p.get('data_source')!r}")
        if pid in seen_ids:
            fail("Duplicate profile_id detected", f"Duplicate ID: {pid}")
        seen_ids.add(pid)

        is_sample = p["data_source"] == SOURCE_SAMPLE
        for str_key in ["full_name", "headline", "current_company", "current_role", "location", "about"] if is_sample else ["full_name"]:
            if not isinstance(p[str_key], str) or len(p[str_key].strip()) < 3:
                fail(f"Invalid basic info field '{str_key}' in {pid}", f"Value: {p[str_key]!r}")

        if not isinstance(p["experiences"], list) or (is_sample and len(p["experiences"]) < 2):
            fail(f"Profile {pid} must have >= 2 work experiences", f"Count: {len(p.get('experiences', []))}")
        for exp in p["experiences"]:
            if not REQUIRED_EXP_KEYS.issubset(exp.keys()):
                fail(f"Experience missing keys in {pid}", f"Missing: {REQUIRED_EXP_KEYS - set(exp.keys())}")
            if is_sample and (not isinstance(exp["duration_months"], int) or exp["duration_months"] <= 0):
                fail(f"Invalid duration_months in {pid}", f"Value: {exp.get('duration_months')}")

        if not isinstance(p["educations"], list) or (is_sample and len(p["educations"]) < 1):
            fail(f"Profile {pid} must have >= 1 education entry", f"Count: {len(p.get('educations', []))}")
        for edu in p["educations"]:
            if not REQUIRED_EDU_KEYS.issubset(edu.keys()):
                fail(f"Education missing keys in {pid}", f"Missing: {REQUIRED_EDU_KEYS - set(edu.keys())}")

        skills = p["skills"]
        if not isinstance(skills, list) or (is_sample and len(skills) < 6):
            fail(f"Profile {pid} must have >= 6 skills", f"Count: {len(skills) if isinstance(skills, list) else 'N/A'}")
        if len(skills) != len(set(skills)):
            fail(f"Duplicate skills found in {pid}", f"Skills: {skills}")

        if not isinstance(p["interests"], list) or (is_sample and len(p["interests"]) < 2):
            fail(f"Profile {pid} must have >= 2 interests", f"Count: {len(p.get('interests', []))}")
        for intr in p["interests"]:
            if not REQUIRED_INT_KEYS.issubset(intr.keys()):
                fail(f"Interest missing keys in {pid}", f"Missing: {REQUIRED_INT_KEYS - set(intr.keys())}")

        if not isinstance(p["activities"], list) or (is_sample and len(p["activities"]) < 3):
            fail(f"Profile {pid} must have >= 3 recent activities", f"Count: {len(p.get('activities', []))}")
        for act in p["activities"]:
            if not REQUIRED_ACT_KEYS.issubset(act.keys()):
                fail(f"Activity missing keys in {pid}", f"Missing: {REQUIRED_ACT_KEYS - set(act.keys())}")
            if act["type"] not in {"post", "comment", "reaction", "repost"}:
                fail(f"Invalid activity type in {pid}", f"Type: {act['type']}")
            for target_id in act["interacted_with"]:
                if target_id not in valid_ids or target_id == pid:
                    fail(f"Invalid interacted_with reference in {pid}", f"Target: {target_id}")

    all_sample = all(p["data_source"] == SOURCE_SAMPLE for p in profiles)
    df_prof = pd.read_csv(PROFILES_CSV)
    if len(df_prof) != len(profiles):
        fail("profiles_summary.csv row count differs from profiles.json", f"Rows: {len(df_prof)}")
    if all_sample and df_prof.isna().sum().sum() > 0:
        fail("profiles_summary.csv contains NaN values", f"NaN count: {df_prof.isna().sum().to_dict()}")

    df_act = pd.read_csv(ACTIVITIES_CSV)
    if all_sample and len(df_act) < 30:
        fail("activities_df.csv must have >= 30 rows", f"Rows: {len(df_act)}")

    print(json.dumps({
        "UNIT": "unit_1_extractor",
        "VERDICT": "PASS",
        "PROFILES_COUNT": len(profiles),
        "ACTIVITIES_COUNT": len(df_act),
        "PARSER_FIXTURES_VERIFIED": True,
        "SCOPE": "src/extractor.py, data/profiles.json, data/profiles_summary.csv"
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
