"""
Skills and role clustering: skill-name normalization, TF-IDF features, spherical K-Means++
with k chosen by silhouette, and skill co-occurrence counts (NumPy only).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple

import numpy as np

RANDOM_SEED = 42
K_CANDIDATES = (3, 4, 5)
KMEANS_RESTARTS = 50


def compute_skill_cooccurrence(profiles: List[Dict]) -> List[Dict]:
    """Computes top co-occurring skill pairs across the 10 profiles."""
    pair_counts = Counter()
    for p in profiles:
        sks = sorted(set(p["skills"]))
        for i in range(len(sks)):
            for j in range(i + 1, len(sks)):
                pair_counts[(sks[i], sks[j])] += 1

    results = []
    for (sa, sb), cnt in sorted(pair_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
        results.append({
            "skill_a": sa,
            "skill_b": sb,
            "cooccurrence_count": int(cnt),
        })
    return results


# Same skill, different spellings: "AWS" / "Amazon Web Services (AWS)", "Python (Programming Language)".
SKILL_SYNONYMS = {
    "aws": "amazon web services", "gcp": "google cloud platform", "google cloud": "google cloud platform",
    "azure": "microsoft azure", "ml": "machine learning", "dl": "deep learning", "ai": "artificial intelligence",
    "nlp": "natural language processing", "cv": "computer vision", "llm": "large language models",
    "llms": "large language models", "large language model": "large language models", "genai": "generative ai",
    "k8s": "kubernetes", "js": "javascript", "ts": "typescript", "postgres": "postgresql",
}


def normalize_skill(name: str) -> str:
    """Lower-case key for a skill: drops "(...)" qualifiers and maps common abbreviations."""
    key = re.sub(r"\s*\([^)]*\)", "", name).strip().lower()
    key = re.sub(r"\s+", " ", key)
    return SKILL_SYNONYMS.get(key, key)


def canonicalize_skills(profiles: List[Dict]) -> None:
    """Rewrites each profile's skills (in memory only) to one display name per normalized skill."""
    forms: Dict[str, Counter] = {}
    for p in profiles:
        for skill in p["skills"]:
            forms.setdefault(normalize_skill(skill), Counter())[skill] += 1
    display = {key: max(c.items(), key=lambda kv: (kv[1], -len(kv[0]), kv[0]))[0] for key, c in forms.items()}
    for p in profiles:
        p["skills"] = list(dict.fromkeys(display[normalize_skill(s)] for s in p["skills"]))


# ---------------------------------------------------------------------------
# 3. Role and skill clustering (TF-IDF + spherical K-Means++)
# ---------------------------------------------------------------------------

def tokenize_profile_features(p: Dict) -> List[str]:
    """Extracts weighted domain tokens from skills, department, role, and activity hashtags."""
    tokens = []
    for sk in p["skills"]:
        norm_sk = re.sub(r"[^a-z0-9]+", "_", sk.lower()).strip("_")
        tokens.extend([f"skill_{norm_sk}"] * 3)
        for word in norm_sk.split("_"):
            if len(word) > 2:
                tokens.append(word)

    if p["department"]:
        dept_norm = re.sub(r"[^a-z0-9]+", "_", p["department"].lower()).strip("_")
        tokens.extend([f"dept_{dept_norm}"] * 3)

    role_words = re.findall(r"[a-zA-Z]{3,}", (p["current_role"] or "").lower())
    tokens.extend(role_words * 2)

    for act in p["activities"]:
        for tag in act["hashtags"]:
            clean_tag = re.sub(r"[^a-z0-9]+", "", tag.lower())
            if clean_tag:
                tokens.append(f"tag_{clean_tag}")

    return tokens


def build_tfidf(profiles: List[Dict]) -> np.ndarray:
    """Returns the L2-normalized TF-IDF matrix (profiles x vocabulary)."""
    docs = [tokenize_profile_features(p) for p in profiles]
    vocab = {tok: i for i, tok in enumerate(sorted({t for doc in docs for t in doc}))}
    tf = np.zeros((len(docs), len(vocab)), dtype=float)
    for i, doc in enumerate(docs):
        for tok, cnt in Counter(doc).items():
            tf[i, vocab[tok]] = 1.0 + math.log(cnt)
    df = (tf > 0).sum(axis=0)
    tfidf = tf * (np.log((1.0 + len(docs)) / (1.0 + df)) + 1.0)
    norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
    return np.divide(tfidf, norms, out=np.zeros_like(tfidf), where=norms > 0)


def spherical_kmeans_pp(X: np.ndarray, k: int, rng: np.random.Generator) -> Tuple[np.ndarray, float]:
    """One K-Means++ run on unit vectors with cosine distance. Returns (labels, inertia)."""
    n = X.shape[0]
    centers = [X[rng.integers(n)]]
    while len(centers) < k:
        d = 1.0 - np.max(X @ np.array(centers).T, axis=1)
        d = np.clip(d, 0.0, None) ** 2
        probs = d / d.sum() if d.sum() > 0 else np.full(n, 1.0 / n)
        centers.append(X[rng.choice(n, p=probs)])
    centroids = np.array(centers)

    labels = np.full(n, -1)
    for _ in range(100):
        new_labels = np.argmax(X @ centroids.T, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c in range(k):
            members = X[labels == c]
            if len(members):
                mean = members.mean(axis=0)
                centroids[c] = mean / max(np.linalg.norm(mean), 1e-12)
    inertia = float(np.sum(1.0 - np.max(X @ centroids.T, axis=1)))
    return labels, inertia


def silhouette(cos_dist: np.ndarray, labels: np.ndarray) -> float:
    """Mean silhouette over all points under a precomputed distance matrix."""
    scores = []
    for i in range(len(labels)):
        same = (labels == labels[i])
        same[i] = False
        if not same.any():
            scores.append(0.0)
            continue
        a = cos_dist[i, same].mean()
        b = min(cos_dist[i, labels == c].mean() for c in set(labels.tolist()) if c != labels[i])
        scores.append((b - a) / max(a, b, 1e-9))
    return float(np.mean(scores))


def name_cluster(cluster_id: int, member_idx: List[int], profiles: List[Dict]) -> str:
    """Names a cluster after the skills that most distinguish it from the other profiles."""
    others = [i for i in range(len(profiles)) if i not in member_idx]
    def rate(idx: List[int], skill: str) -> float:
        return sum(skill in profiles[i]["skills"] for i in idx) / max(len(idx), 1)
    skills = sorted({s for i in member_idx for s in profiles[i]["skills"]})
    top = sorted(skills, key=lambda s: (-(rate(member_idx, s) - rate(others, s)), s))[:3]
    return f"Cluster {cluster_id}: " + (", ".join(top) if top else "no skills listed (grouped by role and activity)")


def compute_clusters(profiles: List[Dict]) -> Dict:
    """
    Selects k by silhouette over K_CANDIDATES, keeping the lowest-inertia run for each k.
    Works in profile_id order, so tied partitions do not depend on the input order.
    """
    profiles = sorted(profiles, key=lambda p: p["profile_id"])
    X = build_tfidf(profiles)
    cos_sim = np.clip(X @ X.T, 0.0, 1.0)
    cos_dist = 1.0 - cos_sim
    np.fill_diagonal(cos_dist, 0.0)
    rng = np.random.default_rng(RANDOM_SEED)

    n = len(profiles)
    candidates = [k for k in K_CANDIDATES if k < n] or ([2] if n >= 3 else [])
    by_k = {}
    for k in candidates:
        runs = [spherical_kmeans_pp(X, k, rng) for _ in range(KMEANS_RESTARTS)]
        runs = [r for r in runs if len(set(r[0].tolist())) == k]
        if not runs:
            continue
        labels = min(runs, key=lambda r: r[1])[0]
        by_k[k] = (labels, silhouette(cos_dist, labels))
    if by_k:
        best_k = max(by_k, key=lambda k: (round(by_k[k][1], 6), -k))
        raw_labels, sil = by_k[best_k]
    else:  # Too few distinct profiles to cluster; silhouette is undefined.
        best_k, raw_labels, sil = 1, np.zeros(n, dtype=int), None

    # Stable numbering: clusters are numbered by first appearance in profile order.
    remap: Dict[int, int] = {}
    for lab in raw_labels.tolist():
        remap.setdefault(lab, len(remap))
    labels = [remap[lab] for lab in raw_labels.tolist()]

    summaries = []
    for c in range(best_k):
        idx = [i for i, lab in enumerate(labels) if lab == c]
        skill_counter = Counter(s for i in idx for s in profiles[i]["skills"])
        pair_sims = [cos_sim[i, j] for i in idx for j in idx if i != j]
        summaries.append({
            "cluster_id": c,
            "cluster_name": name_cluster(c, idx, profiles),
            "member_count": len(idx),
            "members": [
                {"profile_id": profiles[i]["profile_id"], "full_name": profiles[i]["full_name"], "role": profiles[i]["current_role"]}
                for i in idx
            ],
            "dominant_skills": [s for s, _ in sorted(skill_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:6]],
            "avg_intra_cluster_similarity": round(float(np.mean(pair_sims)), 4) if pair_sims else None,
        })
    return {
        "cos_sim": cos_sim,
        "labels": labels,
        "silhouette": sil,
        "silhouette_by_k": {int(k): round(v[1], 4) for k, v in by_k.items()},
        "summaries": summaries,
    }
