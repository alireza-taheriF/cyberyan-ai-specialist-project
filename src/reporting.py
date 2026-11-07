"""
Outputs for people: the three-panel figure (output/graph.png) and the Persian report (output/report.md).
Every statement in the report is computed from the analysis results.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

LAYOUT_SEED = 42
MAX_LABELLED_NODES = 25  # Above this, name boxes and matrix values would overlap.


# ---------------------------------------------------------------------------
# 4. Layout and dashboard
# ---------------------------------------------------------------------------

def compute_spring_layout(W: np.ndarray, clusters: List[int]) -> Dict[int, Tuple[float, float]]:
    """
    Computes clean, well-separated 2D node coordinates combining cluster sector priors
    with strong repulsive spring relaxation so callouts and edge badges never collide.
    """
    n = W.shape[0]
    rng = np.random.default_rng(LAYOUT_SEED)

    num_clusters = max(clusters) + 1
    sector_angles = {c: 2 * math.pi * c / num_clusters + 0.4 for c in range(num_clusters)}
    pos = np.zeros((n, 2), dtype=float)
    strength = W.sum(axis=1)
    max_s = strength.max() if strength.max() > 0 else 1.0

    for i in range(n):
        c = clusters[i]
        base_angle = sector_angles.get(c, 0.0) + rng.uniform(-0.42, 0.42)
        radius = 1.25 - 0.60 * (strength[i] / max_s)
        pos[i, 0] = radius * math.cos(base_angle)
        pos[i, 1] = radius * math.sin(base_angle)

    for _ in range(220):
        disp = np.zeros_like(pos)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                delta = pos[i] - pos[j]
                dist = max(np.linalg.norm(delta), 0.08)
                rep = 0.09 / (dist ** 2)
                disp[i] += (delta / dist) * rep
                if W[i, j] > 0:
                    attr = (dist - 0.75) * 0.05 * W[i, j]
                    disp[i] -= (delta / dist) * attr
        pos += np.clip(disp, -0.05, 0.05)

    pos -= pos.mean(axis=0)
    max_coord = np.abs(pos).max()
    if max_coord > 0:
        pos = pos / max_coord * 0.86

    return {i: (float(pos[i, 0]), float(pos[i, 1])) for i in range(n)}


def _plain(name: str) -> str:
    """Name without emoji, which the plot font cannot draw (e.g. 'Clem Delangue 🤗')."""
    return "".join(ch for ch in name if ord(ch) < 0x2000 or 0x3000 <= ord(ch) < 0x1F000).strip()


def render_visual_dashboard(
    profiles: List[Dict],
    W: np.ndarray,
    edges: List[Dict],
    centralities: Dict[str, np.ndarray],
    clusters: List[int],
    cos_sim: np.ndarray,
    silhouette_score: float,
    cluster_summaries: List[Dict],
    metadata: Dict,
    out_png: str,
):
    """Renders a 3-panel executive analytical figure (`output/graph.png`)."""
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]
    fig = plt.figure(figsize=(22, 13.5), dpi=100, facecolor="#F8FAFC")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.35, 1.0], height_ratios=[1.0, 1.0], wspace=0.22, hspace=0.28)

    palette = ["#2563EB", "#059669", "#D97706", "#7C3AED", "#DC2626"]
    cluster_palette = {s["cluster_id"]: palette[s["cluster_id"]] for s in cluster_summaries}
    cluster_short_labels = {s["cluster_id"]: s["cluster_name"] for s in cluster_summaries}
    id_to_idx = {p["profile_id"]: i for i, p in enumerate(profiles)}
    is_sample = metadata["data_source"] != "live"

    # Panel A: Organizational Network Graph
    ax_graph = fig.add_subplot(gs[:, 0])
    ax_graph.set_facecolor("#FFFFFF")
    pos = compute_spring_layout(W, clusters)
    comp_scores = centralities["composite_centrality_score"]

    # Callout box centers, used to keep edge badges off the name boxes
    callout_centers = []
    for i in range(len(profiles)):
        nx_i, ny_i = pos[i]
        oy = -0.115 if ny_i < 0.62 else 0.115
        callout_centers.append((nx_i, ny_i + oy))

    for e in edges:
        u = id_to_idx[e["source"]]
        v = id_to_idx[e["target"]]
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        w = e["weight"]
        alpha = min(0.85, max(0.18, (w - 0.15) * 1.3))
        lw = 1.0 + 6.5 * (w ** 1.4)
        edge_color = "#64748B" if w < 0.50 else "#1E293B"
        ax_graph.plot([x1, x2], [y1, y2], color=edge_color, linewidth=lw, alpha=alpha, zorder=1)

        # Label strong edges only at a point that clears every node and name box
        if w >= 0.50:
            for ratio in (0.50, 0.36, 0.64, 0.25, 0.75):
                mx = x1 + ratio * (x2 - x1)
                my = y1 + ratio * (y2 - y1)
                min_node_dist = min(math.hypot(mx - pos[k][0], my - pos[k][1]) for k in range(len(profiles)))
                clears_boxes = all(abs(mx - cx) > 0.27 or abs(my - cy) > 0.095 for cx, cy in callout_centers)
                if min_node_dist > 0.11 and clears_boxes:
                    ax_graph.text(
                        mx, my, f"{w:.2f}",
                        fontsize=7.5, fontweight="bold", color="#0F172A",
                        ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.16", facecolor="#F1F5F9", edgecolor="#94A3B8", alpha=0.92),
                        zorder=3
                    )
                    break

    for i, p in enumerate(profiles):
        x, y = pos[i]
        c_id = clusters[i]
        node_size = 580 + 1650 * (comp_scores[i] ** 1.3)
        ax_graph.scatter(
            x, y, s=node_size, color=cluster_palette[c_id],
            edgecolors="#0F172A", linewidths=2.2, alpha=0.96, zorder=4
        )
        ax_graph.text(
            x, y, p["profile_id"].upper(),
            fontsize=9, fontweight="bold", color="#FFFFFF",
            ha="center", va="center", zorder=5
        )
        if len(profiles) > MAX_LABELLED_NODES:
            continue
        offset_y = -0.115 if y < 0.62 else 0.115
        short_role = (p["current_role"] or "").replace("Artificial Intelligence", "AI").replace(" & Governance", "")
        short_role = re.sub(r"\s*\(.*?\)", "", short_role)  # "Staff Engineer (Developer Experience ...)" -> "Staff Engineer"
        if len(short_role) > 30:
            short_role = short_role[:29].rstrip() + "…"
        label_str = f"{_plain(p['full_name'])}\n({short_role})\nScore: {comp_scores[i]:.3f}"
        ax_graph.text(
            x, y + offset_y, label_str,
            fontsize=8.5, fontweight="bold", color="#0F172A",
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.28", facecolor="#FFFFFF", edgecolor=cluster_palette[c_id], lw=1.5, alpha=0.95),
            zorder=6
        )

    ax_graph.set_title(
        f"{metadata['organization']} Organizational Network Graph\n(Node Size = Composite Centrality | Color = ML Cluster | Edge Width = Tie Strength)",
        fontsize=13.5, fontweight="bold", color="#0F172A", pad=14
    )
    ax_graph.set_xlim(-1.18, 1.18)
    ax_graph.set_ylim(-1.42, 1.18)
    ax_graph.axis("off")

    legend_handles = [
        mpatches.Patch(color=cluster_palette[c], label=cluster_short_labels[c])
        for c in sorted(cluster_palette.keys())
    ]
    legend_handles.append(Line2D([0], [0], color="#1E293B", lw=3.5, label="Strong Tie (Weight >= 0.50)"))
    legend_handles.append(Line2D([0], [0], color="#64748B", lw=1.5, label="Weaker Tie (Weight < 0.50)"))
    ax_graph.legend(handles=legend_handles, loc="lower left", frameon=True, facecolor="#F8FAFC", edgecolor="#CBD5E1", fontsize=9.5)

    # Panel B: Multi-Metric Centrality Leaderboard
    ax_bar = fig.add_subplot(gs[0, 1])
    ax_bar.set_facecolor("#FFFFFF")

    order = np.argsort(comp_scores)
    y_pos = np.arange(len(profiles))
    names_ordered = [f"{_plain(profiles[i]['full_name'])} ({profiles[i]['profile_id'].upper()})" for i in order]

    bar_h = 0.20
    ax_bar.barh(y_pos + 1.5 * bar_h, centralities["composite_centrality_score"][order], height=bar_h, label="Composite Influence", color="#1E293B")
    ax_bar.barh(y_pos + 0.5 * bar_h, centralities["degree_centrality"][order], height=bar_h, label="Degree Centrality", color="#2563EB")
    ax_bar.barh(y_pos - 0.5 * bar_h, centralities["betweenness_centrality"][order], height=bar_h, label="Betweenness (Bridge)", color="#D97706")
    ax_bar.barh(y_pos - 1.5 * bar_h, centralities["eigenvector_centrality"][order], height=bar_h, label="Eigenvector Centrality", color="#059669")

    ax_bar.set_yticks(y_pos)
    ax_bar.set_yticklabels(names_ordered, fontsize=9, fontweight="bold", color="#1E293B")
    ax_bar.set_xlim(0, 1.13)
    ax_bar.set_xlabel("Normalized Score [0.0 - 1.0]", fontsize=10, fontweight="bold", color="#334155")
    ax_bar.set_title("Key People Identification: Multi-Metric Centrality Ranking", fontsize=12.5, fontweight="bold", color="#0F172A", pad=10)
    ax_bar.grid(axis="x", linestyle="--", alpha=0.4)
    ax_bar.legend(loc="lower right", fontsize=8.5, frameon=True, facecolor="#F8FAFC")

    for idx_pos, prof_idx in enumerate(order):
        val = comp_scores[prof_idx]
        ax_bar.text(val + 0.015, idx_pos + 1.5 * bar_h, f"{val:.3f}", va="center", fontsize=8, fontweight="bold", color="#0F172A")

    # Panel C: TF-IDF Profile Similarity Matrix (Sorted by Cluster)
    ax_heat = fig.add_subplot(gs[1, 1])
    cluster_order = sorted(range(len(profiles)), key=lambda i: (clusters[i], -comp_scores[i]))
    sim_ordered = cos_sim[np.ix_(cluster_order, cluster_order)]
    labels_ordered = [f"{profiles[i]['profile_id'].upper()}: {_plain(profiles[i]['full_name']).split()[-1]} (C{clusters[i]})" for i in cluster_order]

    im = ax_heat.imshow(sim_ordered, cmap="YlGnBu", vmin=0.0, vmax=1.0, aspect="auto")
    ax_heat.set_xticks(range(len(profiles)))
    ax_heat.set_yticks(range(len(profiles)))
    ax_heat.set_xticklabels(labels_ordered, rotation=38, ha="right", fontsize=8.5, fontweight="bold")
    ax_heat.set_yticklabels(labels_ordered, fontsize=8.5, fontweight="bold")

    for r in range(len(profiles) if len(profiles) <= MAX_LABELLED_NODES else 0):
        for c in range(len(profiles)):
            val = sim_ordered[r, c]
            txt_color = "#FFFFFF" if val > 0.55 else "#0F172A"
            ax_heat.text(c, r, f"{val:.2f}", ha="center", va="center", fontsize=7.5, color=txt_color, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax_heat, fraction=0.046, pad=0.04)
    cbar.set_label("TF-IDF Cosine Similarity", fontsize=9, fontweight="bold")
    ax_heat.set_title(
        f"Role & Skill Clustering Similarity Matrix (K-Means++ k={len(cluster_summaries)}, Silhouette = {'n/a' if silhouette_score is None else format(silhouette_score, '.3f')})",
        fontsize=12, fontweight="bold", color="#0F172A", pad=10
    )

    fig.suptitle(
        "Organizational Network & Role Clustering" + (" — SYNTHETIC SAMPLE DATA, NOT REAL PEOPLE" if is_sample else ""),
        fontsize=16, fontweight="bold", color="#0F172A", y=0.98
    )
    plt.savefig(out_png, dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5. Structured Markdown Analytical Report Generator (`output/report.md`)
# ---------------------------------------------------------------------------

def _names_with_max(ranking: List[Dict], metric: str) -> str:
    """Names everyone tied for the highest value of a metric."""
    top = max(r[metric] for r in ranking)
    if top == 0:
        return "هیچ‌کس (مقدار همه صفر است)"
    return "، ".join(f"`{r['full_name']}`" for r in ranking if r[metric] == top)


def _silhouette_reading(score: float) -> str:
    if score < 0.25:
        return "ساختار خوشه‌ای ضعیف؛ خوشه‌ها را باید گرایش کلی دانست، نه مرز قطعی"
    if score < 0.50:
        return "ساختار خوشه‌ای متوسط"
    return "ساختار خوشه‌ای روشن"


def generate_analytical_report(
    edges: List[Dict],
    ranking: List[Dict],
    clusters: List[Dict],
    skill_cooccurrence: List[Dict],
    metadata: Dict,
    betweenness_sensitivity: Dict[str, str],
    out_md: str,
):
    """Writes the Persian report. Every finding below is computed from the analysis results."""
    sil = metadata["clustering_silhouette_score"]
    zero_bridge = [r["full_name"] for r in ranking if r["betweenness_centrality"] == 0]
    lines = ["# گزارش تحلیل گراف ارتباطی و خوشه‌بندی نقش‌ها", ""]
    if metadata["data_source"] != "live":
        lines += [
            "> **هشدار:** این گزارش روی داده‌ی نمونه‌ی ساختگی اجرا شده است. افراد، سازمان و تعامل‌ها واقعی نیستند "
            "و نتایج فقط درستی روش را نشان می‌دهند، نه یافته‌ای درباره‌ی یک سازمان واقعی.",
            "",
        ]
    elif metadata["organization"] == "No single organization":
        lines += [
            "> **توجه:** این افراد در یک سازمان واحد کار نمی‌کنند؛ گراف شبکه‌ی این فهرست را نشان می‌دهد، نه ساختار یک سازمان.",
            "",
        ]
    if metadata["profiles_with_missing_sections"]:
        lines += [
            "> **داده‌ی ناقص:** برای این پروفایل‌ها بخشی پیدا نشد و تحلیل بدون آن انجام شد: "
            + "، ".join(metadata["profiles_with_missing_sections"]) + ".",
            "",
        ]
    lines += [
        "## ۱. خلاصه شبکه",
        "",
        "| شاخص | مقدار |",
        "| :--- | :---: |",
        f"| منبع داده | `{metadata['data_source']}` |",
        f"| سازمان | `{metadata['organization']}` |",
        f"| تعداد گره‌ها | `{metadata['num_nodes']}` |",
        f"| تعداد یال‌ها | `{metadata['num_edges']}` |",
        f"| چگالی گراف | `{metadata['graph_density']:.4f}` |",
        f"| میانگین درجه | `{metadata['average_degree']:.2f}` |",
        f"| تعداد خوشه‌ها (k) | `{metadata['num_clusters']}` |",
        f"| Silhouette | `{'—' if sil is None else format(sil, '.4f')}` |",
        "",
        "## ۲. افراد کلیدی (Centrality)",
        "",
        "| رتبه | شناسه | نام | نقش | خوشه | Degree | Betweenness | Eigenvector | PageRank | امتیاز ترکیبی |",
        "| :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for rank_idx, r in enumerate(ranking, start=1):
        lines.append(
            f"| {rank_idx} | `{r['profile_id']}` | {r['full_name']} | {r['current_role'] or '—'} | `C{r['cluster_id']}` | "
            f"`{r['degree_centrality']:.4f}` | `{r['betweenness_centrality']:.4f}` | `{r['eigenvector_centrality']:.4f}` | "
            f"`{r['pagerank']:.4f}` | **`{r['composite_centrality_score']:.4f}`** |"
        )
    lines += [
        "",
        "برداشت‌ها:",
        "",
        f"- **بیشترین امتیاز ترکیبی:** `{ranking[0]['full_name']}` با `{ranking[0]['composite_centrality_score']:.4f}`.",
        f"- **قوی‌ترین پل ارتباطی (Betweenness):** {_names_with_max(ranking, 'betweenness_centrality')}.",
        f"- **بیشترین ارتباط مستقیم (Degree):** {_names_with_max(ranking, 'degree_centrality')}.",
        f"- **بیشترین نفوذ از طریق افراد پرنفوذ (Eigenvector):** {_names_with_max(ranking, 'eigenvector_centrality')}.",
    ]
    if zero_bridge:
        lines.append(f"- **بدون نقش پل (Betweenness صفر):** {'، '.join(zero_bridge)}.")
    lines += [
        "",
        "**حساسیت Betweenness به تعریف فاصله:** "
        + " | ".join(f"{label}: {top}" for label, top in betweenness_sensitivity.items())
        + ". اگر این نام‌ها متفاوت باشند، نقش «پل» به تعریف فاصله وابسته است و نباید قطعی تلقی شود.",
        "",
        "## ۳. قوی‌ترین پیوندها در گراف ارتباطی",
        "",
        "وزن‌های به‌کاررفته: " + "، ".join(f"{k}=`{v}`" for k, v in metadata["edge_weights"].items())
        + (" (هیچ تعاملی میان افراد فهرست ثبت نشد، پس وزن Activity صفر و بقیه نرمال شدند)." if metadata["edge_weights"]["activity"] == 0 else "."),
        "",
        "| رتبه | فرد اول | فرد دوم | وزن | Activity | شرکت | مهارت (Jaccard) | شرکت‌های مشترک |",
        "| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ]
    for idx, e in enumerate(edges[:10], start=1):
        shared_c = ", ".join(e["shared_companies"]) or "—"
        lines.append(
            f"| {idx} | {e['source_name']} | {e['target_name']} | **`{e['weight']:.4f}`** | `{e['activity_score']:.4f}` | "
            f"`{e['company_overlap_score']:.4f}` | `{e['skill_jaccard_score']:.4f}` | {shared_c} |"
        )
    by_k = "، ".join(f"k={k}: `{v:.4f}`" for k, v in metadata["silhouette_by_k"].items())
    lines += [
        "",
        "## ۴. خوشه‌بندی نقش‌ها و مهارت‌ها",
        "",
        "تعداد پروفایل‌ها برای خوشه‌بندی کافی نیست." if sil is None else
        f"مقدار k با بیشینه‌کردن Silhouette انتخاب شد ({by_k}). مقدار نهایی `{sil:.4f}` یعنی: {_silhouette_reading(sil)}.",
        "",
        "| خوشه | عنوان (مهارت‌های متمایزکننده) | اعضا | میانگین شباهت درونی | مهارت‌های پرتکرار |",
        "| :---: | :--- | :--- | :---: | :--- |",
    ]
    for c in clusters:
        members = "، ".join(m["full_name"] for m in c["members"])
        intra = "—" if c["avg_intra_cluster_similarity"] is None else f"`{c['avg_intra_cluster_similarity']:.4f}`"
        lines.append(f"| `C{c['cluster_id']}` | {c['cluster_name']} | {members} | {intra} | {'، '.join(c['dominant_skills'])} |")
    lines += [
        "",
        "### جفت‌مهارت‌های پرتکرار",
        "",
        "| رتبه | جفت مهارت | تعداد پروفایل |",
        "| :---: | :--- | :---: |",
    ]
    for idx, sp in enumerate(skill_cooccurrence[:8], start=1):
        lines.append(f"| {idx} | {sp['skill_a']} + {sp['skill_b']} | `{sp['cooccurrence_count']}` |")
    lines += [
        "",
        "## ۵. محدودیت‌ها",
        "",
        "- ضرایب وزن یال و امتیاز ترکیبی انتخاب طراحی‌اند و از داده یاد گرفته نشده‌اند.",
        "- با ۱۰ پروفایل، رتبه‌ها و خوشه‌ها آماری نیستند و با تغییر کوچک داده ممکن است عوض شوند.",
        "- تصویر این نتایج در `output/graph.png` است: گراف، مقایسه‌ی شاخص‌ها و ماتریس شباهت TF-IDF.",
    ]
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
