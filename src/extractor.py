#!/usr/bin/env python3
"""
Turns LinkedIn profile pages into the project's data files.

  --mode replay   (default) parses the pages the browser extension saved in raw_live/
                  (see run.py, src/capture_server.py and src/live_browser.py)
  --mode offline  loads the bundled synthetic sample in sample_data/; no network, used by tests

Writes data/profiles.json (full records), data/profiles_summary.csv (one row per profile) and
data/activities_df.csv (one row per post or interaction). Every record carries `data_source`
("live" or "synthetic_sample"). A field a page does not show is stored as null, never guessed.

Usage:
  python src/extractor.py --urls-file urls.txt
  python src/extractor.py --mode offline
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Tuple

import pandas as pd

import live_browser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("LinkedInExtractor")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_LIVE_DIR = os.path.join(PROJECT_ROOT, "raw_live")
SAMPLE_PROFILES_JSON = os.path.join(PROJECT_ROOT, "sample_data", "synthetic_profiles.json")

SOURCE_LIVE = "live"
SOURCE_SAMPLE = "synthetic_sample"


def load_sample() -> List[Dict[str, Any]]:
    """The fictional 10-person organization used for offline runs and tests."""
    with open(SAMPLE_PROFILES_JSON, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    for p in profiles:
        p["data_source"] = SOURCE_SAMPLE
    return profiles


def export_dataframes(profiles: List[Dict[str, Any]], data_dir: str) -> Tuple[str, str]:
    """Writes the profile summary and the activity table as CSV DataFrames."""
    os.makedirs(data_dir, exist_ok=True)
    summary_rows = []
    activity_rows = []

    for p in profiles:
        summary_rows.append({
            "profile_id": p["profile_id"],
            "public_identifier": p["public_identifier"],
            "full_name": p["full_name"],
            "current_role": p["current_role"],
            "department": p["department"],
            "seniority": p["seniority"],
            "current_company": p["current_company"],
            "location": p["location"],
            "connections_count": p["connections_count"],
            "followers_count": p["followers_count"],
            "total_experience_months": sum(e["duration_months"] or 0 for e in p["experiences"]),
            "past_companies_count": len(p["experiences"]),
            "highest_degree": p["educations"][0]["degree"] if p["educations"] else None,
            "alma_mater": p["educations"][0]["school"] if p["educations"] else None,
            "skills_count": len(p["skills"]),
            "top_skills": "; ".join(p["skills"][:5]),
            "interests_count": len(p["interests"]),
            "activities_count": len(p["activities"]),
            "total_activity_engagement": sum((a["likes_count"] or 0) + (a["comments_count"] or 0) for a in p["activities"]),
            "data_source": p["data_source"],
        })
        for a in p["activities"]:
            activity_rows.append({
                "activity_id": a["activity_id"],
                "author_profile_id": p["profile_id"],
                "author_name": p["full_name"],
                "type": a["type"],
                "timestamp": a["timestamp"],
                "likes_count": a["likes_count"],
                "comments_count": a["comments_count"],
                "interacted_with": ",".join(a["interacted_with"]),
                "hashtags": ",".join(a["hashtags"]),
                "content": a["content"],
            })

    activity_columns = ["activity_id", "author_profile_id", "author_name", "type", "timestamp",
                        "likes_count", "comments_count", "interacted_with", "hashtags", "content"]
    df_profiles = pd.DataFrame(summary_rows).sort_values("profile_id").reset_index(drop=True)
    df_activities = pd.DataFrame(activity_rows, columns=activity_columns)
    df_activities = df_activities.sort_values(["author_profile_id", "activity_id"]).reset_index(drop=True)

    profiles_csv = os.path.join(data_dir, "profiles_summary.csv")
    activities_csv = os.path.join(data_dir, "activities_df.csv")
    df_profiles.to_csv(profiles_csv, index=False, encoding="utf-8")
    df_activities.to_csv(activities_csv, index=False, encoding="utf-8")
    return profiles_csv, activities_csv


def main():
    parser = argparse.ArgumentParser(description="Turn saved LinkedIn profile pages into JSON and CSV data files.")
    parser.add_argument("--mode", choices=["replay", "offline"], default="replay")
    parser.add_argument("--urls-file", default=os.path.join(PROJECT_ROOT, "urls.txt"))
    parser.add_argument("--capture-dir", default=RAW_LIVE_DIR, help="Folder of saved pages (replay mode).")
    args = parser.parse_args()

    if args.mode == "offline":
        profiles = load_sample()
    else:
        try:
            profiles = live_browser.parse_capture_dir(live_browser.read_urls_file(args.urls_file), args.capture_dir)
        except (OSError, ValueError) as exc:
            logger.error(f"{exc}. Nothing was written to data/.")
            sys.exit(2)

    for p in profiles:
        if p.get("missing_sections"):
            logger.warning(f"{p['profile_id']} {p['public_identifier']}: nothing parsed for {p['missing_sections']}")
    profiles.sort(key=lambda x: x["profile_id"])

    os.makedirs(DATA_DIR, exist_ok=True)
    json_path = os.path.join(DATA_DIR, "profiles.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
    profiles_csv, activities_csv = export_dataframes(profiles, DATA_DIR)

    sources = sorted({p["data_source"] for p in profiles})
    logger.info(f"Extracted {len(profiles)} profiles (mode={args.mode}, data_source={sources}).")
    logger.info(f"  -> {json_path}")
    logger.info(f"  -> {profiles_csv}")
    logger.info(f"  -> {activities_csv}")


if __name__ == "__main__":
    main()
