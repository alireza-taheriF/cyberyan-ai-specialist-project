"""
Organizational graph and centrality (NumPy only).

Edge weight between two people:
  W = 0.45*activity + 0.25*company + 0.20*skills + 0.10*education
and key people from degree, betweenness, eigenvector and PageRank centrality.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np

EDGE_MIN_WEIGHT = 0.30


# ---------------------------------------------------------------------------
# 1. Multi-Factor Organizational Graph Construction
# ---------------------------------------------------------------------------

BASE_WEIGHTS = {"activity": 0.45, "company": 0.25, "skills": 0.20, "education": 0.10}


def _org_key(name: str, url: str) -> str:
    """Companies and schools match by their LinkedIn link when known, so 'Google' equals '谷歌'."""
    return url or (name or "").strip().lower()


def build_organizational_graph(profiles: List[Dict]) -> Tuple[np.ndarray, List[Dict], Dict[str, float]]:
    """
    Constructs a symmetric weighted adjacency matrix W (N x N) and detailed edge list.
    Edge weight formula:
      W(u, v) = 0.45 * S_activity(u, v) + 0.25 * S_company(u, v) + 0.20 * S_skills(u, v) + 0.10 * S_edu(u, v)
    When no listed profile interacts with another, the activity term is dropped and the other
    weights are rescaled to sum to 1. Returns W, the edges and the weights actually used.
    """
    n = len(profiles)
    id_to_idx = {p["profile_id"]: i for i, p in enumerate(profiles)}

    # 1. Direct activity interactions (undirected: either direction counts equally)
    raw_act = np.zeros((n, n), dtype=float)
    type_weights = {"post": 1.5, "comment": 1.3, "repost": 1.1, "reaction": 0.9}
    for i, p in enumerate(profiles):
        for act in p["activities"]:
            w_type = type_weights.get(act["type"], 1.0)
            for target_id in act["interacted_with"]:
                if target_id in id_to_idx and id_to_idx[target_id] != i:
                    j = id_to_idx[target_id]
                    raw_act[i, j] += w_type
                    raw_act[j, i] += w_type

    max_act = raw_act.max() if raw_act.max() > 0 else 1.0
    s_act = raw_act / max_act
    weights = dict(BASE_WEIGHTS)
    if raw_act.max() == 0:
        rest = 1.0 - weights.pop("activity")
        weights = {"activity": 0.0, **{k: round(v / rest, 4) for k, v in weights.items()}}

    def companies(p: Dict) -> Dict[str, str]:
        return {_org_key(e["company"], e.get("company_url")): e["company"] for e in p["experiences"] if e["company"]}

    def current_key(p: Dict) -> str:
        exps = p["experiences"]
        return _org_key(exps[0]["company"], exps[0].get("company_url")) if exps and exps[0]["company"] else ""

    # 2. Past & Present Company Overlap
    s_comp = np.zeros((n, n), dtype=float)
    shared_companies_map: Dict[Tuple[int, int], List[str]] = {}
    for i in range(n):
        comps_i = companies(profiles[i])
        for j in range(i + 1, n):
            overlap = sorted(set(comps_i) & set(companies(profiles[j])))
            shared_companies_map[(i, j)] = sorted({comps_i[k] for k in overlap})
            same_current = bool(current_key(profiles[i])) and current_key(profiles[i]) == current_key(profiles[j])
            prior_overlap = [k for k in overlap if k != current_key(profiles[i]) or not same_current]
            # Sharing the current employer counts, but alone it stays below the edge threshold: when
            # everyone works at one company it would otherwise join every pair and flatten centrality.
            score = (0.35 if same_current else 0.0) + (0.65 if prior_overlap else 0.0)
            s_comp[i, j] = s_comp[j, i] = score

    # 3. Skill Jaccard Similarity
    s_skill = np.zeros((n, n), dtype=float)
    shared_skills_map: Dict[Tuple[int, int], List[str]] = {}
    for i in range(n):
        sk_i = set(profiles[i]["skills"])
        for j in range(i + 1, n):
            sk_j = set(profiles[j]["skills"])
            inter = sorted(sk_i & sk_j)
            union = sk_i | sk_j
            shared_skills_map[(i, j)] = inter
            jaccard = len(inter) / len(union) if union else 0.0
            s_skill[i, j] = s_skill[j, i] = jaccard

    # 4. Education Alma Mater Overlap
    s_edu = np.zeros((n, n), dtype=float)
    for i in range(n):
        edu_i = {_org_key(e["school"], e.get("school_url")) for e in profiles[i]["educations"] if e["school"]}
        for j in range(i + 1, n):
            edu_j = {_org_key(e["school"], e.get("school_url")) for e in profiles[j]["educations"] if e["school"]}
            if edu_i & edu_j:
                s_edu[i, j] = s_edu[j, i] = 1.0

    # Combine into composite weight matrix
    W = np.zeros((n, n), dtype=float)
    edges = []

    for i in range(n):
        for j in range(i + 1, n):
            w_val = (
                weights["activity"] * s_act[i, j]
                + weights["company"] * s_comp[i, j]
                + weights["skills"] * s_skill[i, j]
                + weights["education"] * s_edu[i, j]
            )
            if raw_act[i, j] > 0 or w_val >= EDGE_MIN_WEIGHT:
                W[i, j] = W[j, i] = round(float(w_val), 4)
                detail = {
                    "source": profiles[i]["profile_id"],
                    "target": profiles[j]["profile_id"],
                    "source_name": profiles[i]["full_name"],
                    "target_name": profiles[j]["full_name"],
                    "weight": round(float(w_val), 4),
                    "activity_score": round(float(s_act[i, j]), 4),
                    "company_overlap_score": round(float(s_comp[i, j]), 4),
                    "skill_jaccard_score": round(float(s_skill[i, j]), 4),
                    "education_overlap_score": round(float(s_edu[i, j]), 4),
                    "shared_companies": shared_companies_map[(i, j)],
                    "shared_skills": shared_skills_map[(i, j)],
                }
                edges.append(detail)

    edges.sort(key=lambda e: (-e["weight"], e["source"], e["target"]))
    return W, edges, weights


# ---------------------------------------------------------------------------
# 2. Centrality metrics (NumPy only)
# ---------------------------------------------------------------------------

def compute_centrality_metrics(W: np.ndarray, distance_exponent: float = 1.0) -> Dict[str, np.ndarray]:
    """
    Computes degree, weighted degree, betweenness, eigenvector and PageRank centrality from
    a symmetric weight matrix. Shortest paths use distance d(u, v) = 1 / W(u, v)^distance_exponent.
    """
    n = W.shape[0]
    A_bin = (W > 0).astype(float)

    # 1. Degree Centrality (unweighted normalized by N-1)
    deg_centrality = A_bin.sum(axis=1) / max(1, (n - 1))

    # 2. Weighted Degree (Normalized strength in [0, 1])
    raw_strength = W.sum(axis=1)
    max_strength = raw_strength.max() if raw_strength.max() > 0 else 1.0
    weighted_deg = raw_strength / max_strength

    # 3. Weighted shortest-path betweenness
    dist = np.full((n, n), np.inf)
    np.fill_diagonal(dist, 0.0)
    for i in range(n):
        for j in range(n):
            if W[i, j] > 0:
                dist[i, j] = 1.0 / (W[i, j] ** distance_exponent)

    betweenness = np.zeros(n, dtype=float)
    eps = 1e-9
    sp_dist = dist.copy()
    for k in range(n):
        for i in range(n):
            for j in range(n):
                if sp_dist[i, k] + sp_dist[k, j] < sp_dist[i, j] - eps:
                    sp_dist[i, j] = sp_dist[i, k] + sp_dist[k, j]

    for s in range(n):
        for t in range(s + 1, n):
            if np.isinf(sp_dist[s, t]):
                continue
            inter_nodes = [
                v for v in range(n)
                if v not in (s, t) and abs(sp_dist[s, v] + sp_dist[v, t] - sp_dist[s, t]) <= 1e-6
            ]
            for v in inter_nodes:
                betweenness[v] += 1.0

    norm_factor = ((n - 1) * (n - 2)) / 2.0
    if norm_factor > 0:
        betweenness = betweenness / norm_factor
    if betweenness.max() > 0:
        betweenness = betweenness / betweenness.max()

    # 4. Eigenvector Centrality (Power iteration on W)
    v = np.ones(n, dtype=float) / math.sqrt(n)
    for _ in range(200):
        v_next = W @ v
        norm = np.linalg.norm(v_next)
        if norm > 0:
            v_next = v_next / norm
        if np.linalg.norm(v_next - v) < 1e-10:
            v = v_next
            break
        v = v_next
    eig_centrality = v / v.max() if v.max() > 0 else v

    # 5. PageRank (Damping alpha = 0.85)
    alpha = 0.85
    row_sums = W.sum(axis=1, keepdims=True)
    P = np.divide(W, row_sums, out=np.full_like(W, 1.0 / n), where=row_sums > 0)
    pr = np.ones(n, dtype=float) / n
    teleport = np.ones(n, dtype=float) / n
    for _ in range(200):
        pr_next = alpha * (P.T @ pr) + (1.0 - alpha) * teleport
        if np.linalg.norm(pr_next - pr, ord=1) < 1e-10:
            pr = pr_next
            break
        pr = pr_next

    pr_norm = pr / pr.max() if pr.max() > 0 else pr
    composite = (
        0.30 * deg_centrality
        + 0.25 * betweenness
        + 0.25 * eig_centrality
        + 0.20 * pr_norm
    )

    return {
        "degree_centrality": np.round(deg_centrality, 4),
        "weighted_degree": np.round(weighted_deg, 4),
        "betweenness_centrality": np.round(betweenness, 4),
        "eigenvector_centrality": np.round(eig_centrality, 4),
        "pagerank": np.round(pr, 4),
        "composite_centrality_score": np.round(composite, 4),
    }
