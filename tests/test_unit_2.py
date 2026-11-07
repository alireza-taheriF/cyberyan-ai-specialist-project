#!/usr/bin/env python3
"""
Unit 2 Verification Check: ML & Organizational Graph Analyzer
Failure State Name: ERR_U2_GRAPH_OR_ML_INVALID
Exit Code 0 = PASS, Non-Zero = FAIL
"""
import json
import os
import random
import sys
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH_JSON = os.path.join(PROJECT_ROOT, "output", "graph.json")
GRAPH_PNG = os.path.join(PROJECT_ROOT, "output", "graph.png")
REPORT_MD = os.path.join(PROJECT_ROOT, "output", "report.md")
ANALYZER_PY = os.path.join(PROJECT_ROOT, "src", "analyzer.py")
PROFILES_JSON = os.path.join(PROJECT_ROOT, "data", "profiles.json")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import analyzer  # noqa: E402


def fail(reason: str, evidence: str):
    print(json.dumps({
        "UNIT": "unit_2_analyzer",
        "VERDICT": "FAIL",
        "REASON": f"ERR_U2_GRAPH_OR_ML_INVALID: {reason}",
        "EVIDENCE": evidence,
        "SCOPE": "src/analyzer.py, output/graph.json, output/graph.png, output/report.md"
    }, ensure_ascii=False))
    sys.exit(1)


def verify_order_independence():
    """Graph weights and cluster membership must not depend on the input order of profiles."""
    with open(PROFILES_JSON, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    shuffled = profiles[:]
    random.Random(7).shuffle(shuffled)

    def edge_weights(items):
        _, edges, _ = analyzer.build_organizational_graph(items)
        return {frozenset((e["source"], e["target"])): e["weight"] for e in edges}

    def partition(items):
        return {frozenset(m["profile_id"] for m in c["members"]) for c in analyzer.compute_clusters(items)["summaries"]}

    if edge_weights(profiles) != edge_weights(shuffled):
        fail("Edge weights change with profile order", "build_organizational_graph")
    if partition(profiles) != partition(shuffled):
        fail("Clusters change with profile order", "compute_clusters")


def meta_source(gdata):
    return gdata["metadata"].get("data_source")


def main():
    for path in [ANALYZER_PY, GRAPH_JSON, GRAPH_PNG, REPORT_MD]:
        if not os.path.exists(path):
            fail("Missing required output file", f"File not found: {path}")

    with open(GRAPH_JSON, "r", encoding="utf-8") as f:
        try:
            gdata = json.load(f)
        except Exception as e:
            fail("Invalid JSON in graph.json", str(e))

    for key in ["metadata", "nodes", "edges", "centrality_ranking", "clusters", "skill_cooccurrence"]:
        if key not in gdata:
            fail(f"graph.json missing top-level key '{key}'", f"Keys found: {list(gdata.keys())}")

    nodes = gdata["nodes"]
    edges = gdata["edges"]
    ranking = gdata["centrality_ranking"]
    clusters = gdata["clusters"]
    meta = gdata["metadata"]

    with open(PROFILES_JSON, "r", encoding="utf-8") as f:
        expected_nodes = len(json.load(f))
    if len(nodes) != expected_nodes:
        fail("Graph node count differs from profiles.json", f"{len(nodes)} vs {expected_nodes}")
    is_sample = meta_source(gdata) != "live"
    if is_sample and len(edges) < 12:
        fail("Graph must contain >= 12 weighted edges", f"Found {len(edges)}")

    # Verify Centrality Metrics
    required_node_metrics = {
        "degree_centrality", "betweenness_centrality",
        "eigenvector_centrality", "pagerank",
        "weighted_degree", "composite_centrality_score", "cluster_id"
    }
    for n in nodes:
        missing = required_node_metrics - set(n.keys())
        if missing:
            fail(f"Node {n.get('id')} missing centrality/ML metrics", f"Missing: {missing}")
        for m in ["degree_centrality", "betweenness_centrality", "eigenvector_centrality", "pagerank", "composite_centrality_score"]:
            val = n[m]
            if not isinstance(val, (int, float)) or val < 0.0 or val > 1.0001:
                fail(f"Metric {m} out of [0, 1] bounds on node {n.get('id')}", f"Value: {val}")

    # Verify deterministic descending sort of centrality_ranking
    scores = [r["composite_centrality_score"] for r in ranking]
    if scores != sorted(scores, reverse=True):
        fail("centrality_ranking is not sorted descending by composite_centrality_score", f"Scores: {scores}")

    # Verify ML clustering quality
    sil_score = meta.get("clustering_silhouette_score", -1.0)
    if is_sample and (not isinstance(sil_score, (int, float)) or sil_score < 0.15):
        fail("ML clustering silhouette score below threshold 0.15", f"Silhouette: {sil_score}")
    if len(clusters) > 5:
        fail("Cluster count must not exceed 5", f"Clusters count: {len(clusters)}")
    by_k = meta.get("silhouette_by_k", {})
    if by_k and (str(len(clusters)) not in by_k or by_k[str(len(clusters))] != max(by_k.values())):
        fail("Chosen k does not have the best silhouette", f"k={len(clusters)}, {by_k}")
    verify_order_independence()

    # Verify graph.png image resolution and file size
    if os.path.getsize(GRAPH_PNG) < 40_000:
        fail("graph.png file size too small (< 40KB)", f"Size: {os.path.getsize(GRAPH_PNG)} bytes")
    with Image.open(GRAPH_PNG) as img:
        w, h = img.size
        if w < 1200 or h < 800:
            fail("graph.png resolution below 1200x800", f"Size: {w}x{h}")

    # Verify report.md content
    with open(REPORT_MD, "r", encoding="utf-8") as f:
        report_text = f.read()
    if len(report_text) < 2000:
        fail("report.md is too short (< 2000 chars)", f"Length: {len(report_text)}")
    for required_term in ["Centrality", "Betweenness", "PageRank", "خوشه‌بندی", "گراف ارتباطی"]:
        if required_term not in report_text:
            fail(f"report.md missing required analytical term '{required_term}'", "Term absent")
    if meta.get("data_source") != "live" and "ساختگی" not in report_text:
        fail("report.md does not disclose synthetic data", str(meta.get("data_source")))
    best = max(nodes, key=lambda x: x["betweenness_centrality"])
    top_bridge = best["full_name"] if best["betweenness_centrality"] > 0 else "هیچ‌کس"
    bridge_line = next((l for l in report_text.splitlines() if "قوی‌ترین پل ارتباطی" in l), "")
    if top_bridge not in bridge_line:
        fail("Report names the wrong top bridge", f"Expected {top_bridge}; line: {bridge_line}")

    print(json.dumps({
        "UNIT": "unit_2_analyzer",
        "VERDICT": "PASS",
        "NODES": len(nodes),
        "EDGES": len(edges),
        "SILHOUETTE_SCORE": sil_score,
        "IMAGE_SIZE": f"{w}x{h}",
        "SCOPE": "src/analyzer.py, output/graph.json, output/graph.png, output/report.md"
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
