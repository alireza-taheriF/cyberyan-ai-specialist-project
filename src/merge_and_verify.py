#!/usr/bin/env python3
"""
Cross-checks the extraction and analysis outputs, sorts them deterministically, and builds
the deliverable at `dist/cyberyan_ai_specialist_project.zip`.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
ZIP_NAME = "cyberyan_ai_specialist_project.zip"
EXCLUDED_FILES: set = set()
# raw_live holds full logged-in pages, so only the parsed data/ ships.
EXCLUDED_DIRS = {"dist", "__pycache__", "raw_live", "artifacts", ".venv", ".browser_profile"}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def merge_dedupe_sort_compare() -> dict:
    profiles_path = os.path.join(PROJECT_ROOT, "data", "profiles.json")
    summary_csv_path = os.path.join(PROJECT_ROOT, "data", "profiles_summary.csv")
    activities_csv_path = os.path.join(PROJECT_ROOT, "data", "activities_df.csv")
    graph_json_path = os.path.join(PROJECT_ROOT, "output", "graph.json")

    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    # Deduplicate profiles by profile_id and sort ascending
    dedup_profiles_map = {}
    for p in profiles:
        pid = p["profile_id"]
        # Deduplicate skills while preserving order
        p["skills"] = list(dict.fromkeys(p["skills"]))
        dedup_profiles_map[pid] = p

    sorted_profiles = [dedup_profiles_map[k] for k in sorted(dedup_profiles_map.keys())]
    with open(profiles_path, "w", encoding="utf-8") as f:
        json.dump(sorted_profiles, f, ensure_ascii=False, indent=2)

    # Deduplicate and deterministically sort CSV DataFrames
    df_sum = pd.read_csv(summary_csv_path).drop_duplicates(subset=["profile_id"]).sort_values("profile_id").reset_index(drop=True)
    df_sum.to_csv(summary_csv_path, index=False, encoding="utf-8")

    df_act = pd.read_csv(activities_csv_path).drop_duplicates(subset=["activity_id"]).sort_values(["author_profile_id", "activity_id"]).reset_index(drop=True)
    df_act.to_csv(activities_csv_path, index=False, encoding="utf-8")

    # Cross-compare profile IDs between Unit 1 (`profiles.json`, CSVs) and Unit 2 (`graph.json`)
    with open(graph_json_path, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    u1_ids = [p["profile_id"] for p in sorted_profiles]
    u1_csv_ids = df_sum["profile_id"].tolist()
    u2_node_ids = sorted([n["profile_id"] for n in graph_data["nodes"]])
    u2_rank_ids = sorted([r["profile_id"] for r in graph_data["centrality_ranking"]])

    if not (u1_ids == u1_csv_ids == u2_node_ids == u2_rank_ids):
        raise AssertionError(f"Cross-unit ID mismatch: U1={u1_ids}, CSV={u1_csv_ids}, U2_nodes={u2_node_ids}")

    # Deduplicate and deterministically sort graph edges and centrality ranking
    edge_map = {}
    for e in graph_data["edges"]:
        u, v = sorted([e["source"], e["target"]])
        edge_map[(u, v)] = e
    graph_data["edges"] = sorted(edge_map.values(), key=lambda x: (-x["weight"], x["source"], x["target"]))
    graph_data["centrality_ranking"] = sorted(
        graph_data["centrality_ranking"],
        key=lambda x: (-x["composite_centrality_score"], -x["degree_centrality"], x["profile_id"])
    )

    with open(graph_json_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)

    return {
        "verified_profile_ids": u1_ids,
        "deduped_activities_count": len(df_act),
        "deduped_edges_count": len(graph_data["edges"]),
    }


def package_deliverables() -> str:
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_path = os.path.join(DIST_DIR, ZIP_NAME)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith("."))
            for file in sorted(files):
                if file.endswith(".pyc") or file.startswith(".") or file in EXCLUDED_FILES:
                    continue
                abs_path = os.path.join(root, file)
                zf.write(abs_path, arcname=os.path.relpath(abs_path, PROJECT_ROOT))
    return zip_path


def main():
    stats = merge_dedupe_sort_compare()
    zip_path = package_deliverables()
    print(json.dumps({
        "UNIT": "unit_5_merge_package",
        "VERDICT": "PASS",
        "MERGE_STATS": stats,
        "ZIP_PATH": zip_path,
        "ZIP_SHA256": sha256_file(zip_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
