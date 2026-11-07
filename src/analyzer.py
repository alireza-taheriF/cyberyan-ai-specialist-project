#!/usr/bin/env python3
"""
Graph and ML analysis of `data/profiles.json` (Cyberyan AI Specialist assessment).

  1. Weighted organizational graph and key people by centrality   -> graph_analysis.py
  2. Role/skill clustering: TF-IDF + K-Means++, k by silhouette     -> clustering.py
  3. Figure and Persian report                                      -> reporting.py

Writes `output/graph.json`, `output/graph.png` and `output/report.md`.
"""

from __future__ import annotations

import json
import os
from collections import Counter

from clustering import KMEANS_RESTARTS, RANDOM_SEED, canonicalize_skills, compute_clusters, compute_skill_cooccurrence
from graph_analysis import build_organizational_graph, compute_centrality_metrics
from reporting import generate_analytical_report, render_visual_dashboard

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_JSON = os.path.join(PROJECT_ROOT, "data", "profiles.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(PROFILES_JSON, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    profiles.sort(key=lambda x: x["profile_id"])
    canonicalize_skills(profiles)
    n = len(profiles)

    W, edges, edge_weights = build_organizational_graph(profiles)
    centralities = compute_centrality_metrics(W)
    clustering = compute_clusters(profiles)
    cos_sim, cluster_labels = clustering["cos_sim"], clustering["labels"]
    silhouette_score, cluster_summaries = clustering["silhouette"], clustering["summaries"]

    def top_bridge(exponent: float) -> str:
        scores = compute_centrality_metrics(W, distance_exponent=exponent)["betweenness_centrality"]
        if scores.max() == 0:
            return "هیچ‌کس"
        return "، ".join(profiles[i]["full_name"] for i in range(n) if scores[i] == scores.max())

    betweenness_sensitivity = {"d=1/W": top_bridge(1.0), "d=1/W^2": top_bridge(2.0), "d=1/W^2.5": top_bridge(2.5)}

    nodes = []
    for i, p in enumerate(profiles):
        nodes.append({
            "id": p["profile_id"],
            "profile_id": p["profile_id"],
            "full_name": p["full_name"],
            "current_role": p["current_role"],
            "department": p["department"],
            "seniority": p["seniority"],
            "current_company": p["current_company"],
            "skills": p["skills"],
            "cluster_id": int(cluster_labels[i]),
            "degree_centrality": float(centralities["degree_centrality"][i]),
            "weighted_degree": float(centralities["weighted_degree"][i]),
            "betweenness_centrality": float(centralities["betweenness_centrality"][i]),
            "eigenvector_centrality": float(centralities["eigenvector_centrality"][i]),
            "pagerank": float(centralities["pagerank"][i]),
            "composite_centrality_score": float(centralities["composite_centrality_score"][i]),
        })

    centrality_ranking = sorted(
        nodes,
        key=lambda x: (-x["composite_centrality_score"], -x["degree_centrality"], x["profile_id"])
    )

    skill_cooccurrence = compute_skill_cooccurrence(profiles)

    max_possible_edges = n * (n - 1) / 2.0
    graph_density = len(edges) / max_possible_edges if max_possible_edges > 0 else 0.0
    avg_degree = (2.0 * len(edges)) / n if n > 0 else 0.0

    sources = {p["data_source"] for p in profiles}
    companies = Counter(p["current_company"] for p in profiles if p["current_company"])
    metadata = {
        "data_source": sources.pop() if len(sources) == 1 else "mixed",
        "organization": companies.most_common(1)[0][0] if companies and companies.most_common(1)[0][1] > n / 2 else "No single organization",
        "num_nodes": n,
        "num_edges": len(edges),
        "graph_density": round(float(graph_density), 4),
        "average_degree": round(float(avg_degree), 4),
        "num_clusters": len(cluster_summaries),
        "edge_weights": edge_weights,
        "clustering_algorithm": f"TF-IDF + spherical K-Means++ (seed={RANDOM_SEED}, restarts={KMEANS_RESTARTS})",
        "silhouette_by_k": clustering["silhouette_by_k"],
        "profiles_with_missing_sections": [p["full_name"] for p in profiles if p.get("missing_sections")],
        "clustering_silhouette_score": None if silhouette_score is None else round(float(silhouette_score), 4),
    }

    graph_payload = {
        "metadata": metadata,
        "nodes": nodes,
        "edges": edges,
        "centrality_ranking": centrality_ranking,
        "clusters": cluster_summaries,
        "skill_cooccurrence": skill_cooccurrence,
    }

    graph_json_path = os.path.join(OUTPUT_DIR, "graph.json")
    with open(graph_json_path, "w", encoding="utf-8") as f:
        json.dump(graph_payload, f, ensure_ascii=False, indent=2)

    graph_png_path = os.path.join(OUTPUT_DIR, "graph.png")
    render_visual_dashboard(
        profiles=profiles,
        W=W,
        edges=edges,
        centralities=centralities,
        clusters=cluster_labels,
        cos_sim=cos_sim,
        silhouette_score=silhouette_score,
        cluster_summaries=cluster_summaries,
        metadata=metadata,
        out_png=graph_png_path,
    )

    report_md_path = os.path.join(OUTPUT_DIR, "report.md")
    generate_analytical_report(
        edges=edges,
        ranking=centrality_ranking,
        clusters=cluster_summaries,
        skill_cooccurrence=skill_cooccurrence,
        metadata=metadata,
        betweenness_sensitivity=betweenness_sensitivity,
        out_md=report_md_path,
    )

    print(f"[Analyzer] Successfully analyzed {n} profiles and {len(edges)} organizational edges.")
    print(f"  -> Top Key Person: {centrality_ranking[0]['full_name']} (Score: {centrality_ranking[0]['composite_centrality_score']:.4f})")
    print(f"  -> ML Clustering Silhouette Score: {silhouette_score}")
    print(f"  -> Graph JSON: {graph_json_path}")
    print(f"  -> Graph PNG:  {graph_png_path}")
    print(f"  -> Report MD:  {report_md_path}")


if __name__ == "__main__":
    main()
