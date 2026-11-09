"""Preliminary summary figure (needs output/code_panel_state.csv).

    python analysis/adult_dental_spillover/figure.py

Writes output/fig_preliminary.png and .pdf. Intervals are ±1.96 placebo SDs
from the permutation distribution (approximate 95%).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import design as D
import prelim as P

INK, MUTED, GRID, BLUE = "#0b0b0b", "#52514e", "#e6e5e1", "#2a78d6"


def style(ax) -> None:
    ax.tick_params(colors=MUTED, labelsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)


def event_panel(ax, band, title: str, r: pd.Series) -> None:
    tp, lo, hi = band
    x = tp.index.values
    ax.fill_between(x, lo.values, hi.values, color=GRID, lw=0, label="Placebo 90% band")
    ax.plot(x, tp.mean(axis=1).values, color=BLUE, lw=2, label="Mean of 6 adopting states")
    ax.axvline(-0.5, color=MUTED, lw=1, ls="--")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_title(f"{title}\n{r.pct_of_baseline:+.0f}% of baseline, {P.fmt_p(r.perm_p)}", loc="left", fontsize=10, color=INK)
    ax.set_xlabel("Months since adult benefit start", fontsize=8.5, color=MUTED)
    ax.set_ylabel("Claims per 100 baseline dental claims", fontsize=8.5, color=MUTED)
    style(ax)


def main() -> None:
    if not P.CODE_PANEL.exists():
        raise SystemExit("run build_code_panel.py first")
    outcomes = P.load_category()
    outcomes.update(P.load_code(outcomes["total"]))
    design = D.build(outcomes["total"])
    res = pd.read_csv(P.OUT / "did_estimates.csv")
    pooled = res[res.state == "POOLED"].set_index("outcome")

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3), gridspec_kw={"width_ratios": [1, 1, 0.9]})
    for ax, y, title in [(axes[0], "total", "A. All dental claims"), (axes[1], "code_child", "B. Children's procedures")]:
        _, band = P.estimate(outcomes[y], outcomes["total"], design)
        event_panel(ax, band, title, pooled.loc[y])
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")

    # C. Child effect by state and by dentist type, % of own baseline
    ax = axes[2]
    child = res[res.outcome == "code_child"].copy()
    rows = [(s, child[child.state == s].iloc[0]) for s in child.state if s != "POOLED"]
    rows += [("All 6 states", pooled.loc["code_child"]),
             ("General dentists", pooled.loc["code_child_general"]),
             ("Pediatric dentists", pooled.loc["code_child_pediatric"])]  # fmt: skip
    labels, ys = [], []
    for i, (lab, r) in enumerate(rows[::-1]):
        est = 100 * r.did / r.baseline
        half = 100 * 1.96 * r.placebo_sd / r.baseline
        bold = lab == "All 6 states"
        ax.plot([est - half, est + half], [i, i], color=INK if bold else MUTED, lw=1.5)
        ax.plot(est, i, "D" if bold else "o", color=INK if bold else BLUE, ms=7 if bold else 6)
        labels.append(lab)
        ys.append(i)
    ax.axhline(2.5, color=GRID, lw=1)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_yticks(ys, labels, fontsize=8.5, color=INK)
    ax.set_xlabel("Change in children's procedures, % of own baseline", fontsize=8.5, color=MUTED)
    ax.set_title("C. Children's procedures by state and dentist type\nwith approximate 95% intervals", loc="left", fontsize=10, color=INK)
    style(ax)

    fig.suptitle(
        "Adding adult Medicaid dental coverage raised total dental claims; children's care did not fall (preliminary)",
        x=0.01, ha="left", fontsize=11.5, color=INK,
    )  # fmt: skip
    fig.text(
        0.01, 0.005,
        "Stacked DiD, 6 adopting states (VA, ME, MD, TN, HI, NH) vs 26-36 clean controls each. HHS Medicaid provider "
        "spending data 2018-2024, linked by CHOMP. Children's procedures = child-specific CDT codes.",
        fontsize=7.5, color=MUTED,
    )  # fmt: skip
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    for ext in ("png", "pdf"):
        fig.savefig(P.OUT / f"fig_preliminary.{ext}", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
