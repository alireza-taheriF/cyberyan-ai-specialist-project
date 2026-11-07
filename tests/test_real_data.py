#!/usr/bin/env python3
"""
Checks on real (live) data: extraction accuracy, graph integrity and README consistency.
Uses only data/, output/ and README.md, so it also runs from the ZIP. On the synthetic sample
it reports SKIPPED and passes. Exit Code 0 = PASS, Non-Zero = FAIL
"""
import json
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from reporting import _plain  # noqa: E402

PROFILES_JSON = os.path.join(PROJECT_ROOT, "data", "profiles.json")
GRAPH_JSON = os.path.join(PROJECT_ROOT, "output", "graph.json")
README_MD = os.path.join(PROJECT_ROOT, "README.md")
SECTIONS = ("experiences", "educations", "skills", "interests", "activities")
MIN_SECTION_COVERAGE = 0.8  # Share of profiles that must have each section.


def fail(reason, evidence=""):
    print(json.dumps({"UNIT": "real_data", "VERDICT": "FAIL", "REASON": reason, "EVIDENCE": str(evidence)}, ensure_ascii=False))
    sys.exit(1)


def check_extraction(profiles):
    """Parsed counts must equal the counts LinkedIn prints, and most profiles must have every section."""
    mismatched = {
        p["full_name"]: (len(p["skills"]), p["linkedin_counts"]["Skills"])
        for p in profiles
        if "Skills" in p.get("linkedin_counts", {}) and len(p["skills"]) != p["linkedin_counts"]["Skills"]
    }
    if mismatched:
        fail("Parsed skills differ from LinkedIn's own count (parsed, LinkedIn)", mismatched)
    for section in SECTIONS:
        share = sum(bool(p[section]) for p in profiles) / len(profiles)
        if share < MIN_SECTION_COVERAGE:
            fail(f"Only {share:.0%} of profiles have {section}", [p["full_name"] for p in profiles if not p[section]])
    for p in profiles:
        missing = [s for s in SECTIONS if not p[s]]
        if sorted(missing) != sorted(p.get("missing_sections", [])):
            fail("missing_sections does not match the data", (p["full_name"], missing, p.get("missing_sections")))


def check_graph(profiles, graph):
    """Every activity edge must come from a recorded interaction, and the graph must not be trivial."""
    ids = {p["profile_id"] for p in profiles}
    linked = set()
    for p in profiles:
        for activity in p["activities"]:
            for other in activity["interacted_with"]:
                if other not in ids or other == p["profile_id"]:
                    fail("interacted_with points outside the list or to the author", (p["full_name"], other))
                linked.add(frozenset((p["profile_id"], other)))
    for edge in graph["edges"]:
        if edge["activity_score"] > 0 and frozenset((edge["source"], edge["target"])) not in linked:
            fail("Edge has an activity score without a recorded interaction", edge)
    density = graph["metadata"]["graph_density"]
    if len(profiles) >= 4 and not 0 < density < 1:
        fail("Graph is empty or complete, so centrality cannot tell people apart", density)


def check_readme(graph):
    """The README's key results must match the current analysis."""
    with open(README_MD, "r", encoding="utf-8") as f:
        readme = f.read().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    match = re.search(r"## نتایج کلیدی(.*?)\n## ", readme, re.S)
    if not match:
        fail("README has no key-results section")
    section = match.group(1)
    top = _plain(graph["centrality_ranking"][0]["full_name"])
    if top not in section:
        fail("README names a different key person than the analysis", top)
    edges = graph["metadata"]["num_edges"]
    if not re.search(rf"\b{edges} یال", section):
        fail("README edge count differs from the analysis", edges)


def main():
    with open(PROFILES_JSON, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    if any(p.get("data_source") != "live" for p in profiles):
        print(json.dumps({"UNIT": "real_data", "VERDICT": "PASS", "NOTE": "SKIPPED: data is not live"}))
        return
    with open(GRAPH_JSON, "r", encoding="utf-8") as f:
        graph = json.load(f)
    check_extraction(profiles)
    check_graph(profiles, graph)
    check_readme(graph)
    print(json.dumps({"UNIT": "real_data", "VERDICT": "PASS", "PROFILES": len(profiles),
                      "EDGES": graph["metadata"]["num_edges"]}))


if __name__ == "__main__":
    main()
