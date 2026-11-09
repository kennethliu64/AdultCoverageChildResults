"""Preliminary analysis: adult Medicaid dental benefit adoption and children's care.

Uses only files already shipped in this repo (category-level monthly state
aggregates). Code-level outcomes are out of reach here; see README.md for
what this can and cannot answer.

    python analysis/adult_dental_spillover/prelim.py

Writes CSVs and PNGs to analysis/adult_dental_spillover/output/.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "public/data/provider_procedure_category_aggregate_monthly_state.json"
OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(exist_ok=True)

# Adoption month of a comprehensive / extensive adult benefit. PROVISIONAL:
# verify each date against the state plan amendment before relying on it.
TREATED = {
    "VA": "2021-07",
    "ME": "2022-07",
    "MD": "2023-01",
    "TN": "2023-01",
    "NH": "2023-04",
}

# Controls: no reporting break in total claims 2018-2024 and no jump in the
# adult-marker share (screen in screen_states()). Also provisional; a state
# that changed adult benefits without moving these categories would slip in.
CONTROLS = [
    "AK", "AL", "AR", "CT", "GA", "IA", "KS", "LA", "MA", "MS",
    "NC", "NJ", "NM", "NY", "OR", "RI", "WA", "WI", "WY",
]  # fmt: skip

# Ortho is sparse in several controls (KS and OR report none); for that outcome
# keep controls with >= 250 ortho claims in every month 2018-01..2020-02.
ORTHO_CONTROLS = ["CT", "GA", "IA", "MA", "MS", "NC", "NJ", "NM", "NY", "RI", "WA", "WI"]

ADULT = ["Periodontics", "Prosthodontics (removable)", "Prosthodontics (fixed)", "Implant Services"]
START, END = "2018-01", "2024-09"  # END drops the Nov/Dec 2024 lag months (L02)
COVID = ("2020-03", "2020-06")  # shutdown months, dropped from estimation
PRE, POST = 24, 18  # event window, months
RNG = np.random.default_rng(20261109)
N_DRAWS = 5000

OUTCOMES = {
    "adult_markers": "Adult-marker claims (perio, prosthodontics, implants)",
    "total": "All dental claims",
    "prev_diag": "Preventive + diagnostic claims",
    "ortho": "Orthodontic claims (child-only proxy)",
    "benes_total": "Beneficiary-months, all categories",
}


def load() -> pd.DataFrame:
    rows = []
    with SRC.open() as f:
        for line in f:
            for st, recs in json.loads(line).items():
                for r in recs:
                    rows.append((st, r["year_month"], r["category"], r["total_claims"], r["total_beneficiaries_served"]))
    df = pd.DataFrame(rows, columns=["state", "ym", "cat", "claims", "benes"])
    df = df[(df.ym >= START) & (df.ym <= END)]
    g = df.groupby(["state", "ym"])
    panel = pd.DataFrame(
        {
            "total": g.claims.sum(),
            "benes_total": g.benes.sum(),
            "adult_markers": df[df.cat.isin(ADULT)].groupby(["state", "ym"]).claims.sum(),
            "prev_diag": df[df.cat.isin(["Preventive", "Diagnostic"])].groupby(["state", "ym"]).claims.sum(),
            "ortho": df[df.cat == "Orthodontics"].groupby(["state", "ym"]).claims.sum(),
        }
    ).fillna(0)
    return panel.reset_index()


def screen_states(panel: pd.DataFrame) -> pd.DataFrame:
    """Half-year total claims and adult-marker share, plus break flags."""
    p = panel.copy()
    p["half"] = p.ym.str[:4] + np.where(p.ym.str[5:7].astype(int) <= 6, "H1", "H2")
    h = p.groupby(["state", "half"])[["total", "adult_markers"]].sum()
    h = h[h.index.get_level_values("half") != "2024H2"]  # partial half
    tot = h.total.unstack()
    share = (h.adult_markers / h.total * 100).unstack()
    covid = ["2020H1"]
    lr = np.log(tot.drop(columns=covid).replace(0, np.nan)).diff(axis=1).abs()
    out = pd.DataFrame(
        {
            "max_abs_log_jump_total": lr.max(axis=1).round(2),
            "adult_share_pre2021": share.loc[:, :"2020H2"].mean(axis=1).round(2),
            "adult_share_2023_24": share.loc[:, "2023H1":].mean(axis=1).round(2),
        }
    )
    out["role"] = np.where(out.index.isin(TREATED), "treated", np.where(out.index.isin(CONTROLS), "control", "excluded"))
    return out.sort_values(["role", "max_abs_log_jump_total"])


def wide(panel: pd.DataFrame, y: str) -> pd.DataFrame:
    w = panel.pivot(index="ym", columns="state", values=y).fillna(0)
    w = np.log1p(w)
    w.loc[(w.index >= COVID[0]) & (w.index <= COVID[1])] = np.nan
    return w


def months(d: str, k: int) -> str:
    return (pd.Period(d, "M") + k).strftime("%Y-%m")


def did(w: pd.DataFrame, s: str, d: str, controls: list[str]) -> float:
    pre = w.loc[months(d, -PRE) : months(d, -1)]
    post = w.loc[d : months(d, POST - 1)]
    gap_pre = (pre[s] - pre[controls].mean(axis=1)).mean()
    gap_post = (post[s] - post[controls].mean(axis=1)).mean()
    return gap_post - gap_pre


def event_path(w: pd.DataFrame, s: str, d: str, controls: list[str]) -> pd.Series:
    ks = range(-PRE, POST)
    gap = pd.Series({k: (w.loc[months(d, k), s] - w.loc[months(d, k), controls].mean()) for k in ks})
    return gap - gap.loc[-12:-1].mean()


def estimates(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows, paths = [], {}
    for y in OUTCOMES:
        w = wide(panel, y)
        ctl = ORTHO_CONTROLS if y == "ortho" else CONTROLS
        per_state = {s: did(w, s, d, ctl) for s, d in TREATED.items()}
        # Placebo: each control as pseudo-treated at each treated date, vs the other controls
        plac = {
            (c, s): did(w, c, d, [x for x in ctl if x != c]) for s, d in TREATED.items() for c in ctl
        }
        for s, est in per_state.items():
            dist = np.array([v for (c, ss), v in plac.items() if ss == s])
            rows.append(
                {
                    "outcome": y,
                    "state": s,
                    "adopt": TREATED[s],
                    "did_log": est,
                    "pct": 100 * (np.exp(est) - 1),
                    "perm_p": (1 + (np.abs(dist) >= abs(est)).sum()) / (1 + len(dist)),
                    "placebo_sd": dist.std(ddof=1),
                }
            )
        # Pooled: mean over the 5 treated; placebo draws 5 distinct controls, one per date
        pooled = np.mean(list(per_state.values()))
        draws = np.empty(N_DRAWS)
        for i in range(N_DRAWS):
            pick = RNG.choice(ctl, size=len(TREATED), replace=False)
            draws[i] = np.mean([plac[(c, s)] for c, s in zip(pick, TREATED)])
        rows.append(
            {
                "outcome": y,
                "state": "POOLED",
                "adopt": "",
                "did_log": pooled,
                "pct": 100 * (np.exp(pooled) - 1),
                "perm_p": (1 + (np.abs(draws) >= abs(pooled)).sum()) / (1 + N_DRAWS),
                "placebo_sd": draws.std(ddof=1),
            }
        )
        # Event paths: treated average and placebo band
        tp = pd.concat({s: event_path(w, s, d, ctl) for s, d in TREATED.items()}, axis=1)
        cp = {
            (c, s): event_path(w, c, d, [x for x in ctl if x != c]) for s, d in TREATED.items() for c in ctl
        }
        band = []
        for _ in range(1000):
            pick = RNG.choice(ctl, size=len(TREATED), replace=False)
            band.append(pd.concat([cp[(c, s)] for c, s in zip(pick, TREATED)], axis=1).mean(axis=1))
        band = pd.concat(band, axis=1)
        paths[y] = (tp, band.quantile(0.05, axis=1), band.quantile(0.95, axis=1))
    res = pd.DataFrame(rows)
    # Minimum detectable effect, 80% power, two-sided 5%: 2.8 x placebo SD
    res["mde_log"] = 2.8 * res.placebo_sd
    res["mde_pct"] = 100 * (np.exp(res.mde_log) - 1)
    return res, paths


def plot(paths: dict, res: pd.DataFrame) -> None:
    ink, muted, grid, s1 = "#0b0b0b", "#52514e", "#e6e5e1", "#2a78d6"
    keys = ["adult_markers", "total", "prev_diag", "ortho"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True)
    for ax, y in zip(axes.flat, keys):
        tp, lo, hi = paths[y]
        x = tp.index.values
        ax.fill_between(x, lo.values, hi.values, color=grid, lw=0, label="Placebo 90% band (control states)")
        ax.plot(x, tp.mean(axis=1).values, color=s1, lw=2, label="Mean of 5 adopting states")
        ax.axvline(-0.5, color=muted, lw=1, ls="--")
        ax.axhline(0, color=muted, lw=0.8)
        r = res[(res.outcome == y) & (res.state == "POOLED")].iloc[0]
        ax.set_title(
            f"{OUTCOMES[y]}\npooled DiD {r.pct:+.1f}%, permutation p={r.perm_p:.3f}", fontsize=10, color=ink, loc="left"
        )
        ax.tick_params(colors=muted, labelsize=8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.spines["left"].set_color(grid)
        ax.spines["bottom"].set_color(grid)
        ax.set_ylabel("log gap vs controls\n(normalized to months -12..-1)", fontsize=8, color=muted)
    for ax in axes[1]:
        ax.set_xlabel("Months since adult benefit start", fontsize=9, color=muted)
    axes[0, 0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle(
        "Adult Medicaid dental benefit adoption: VA, ME, MD, TN, NH (category-level, preliminary)",
        fontsize=11,
        color=ink,
        x=0.01,
        ha="left",
    )
    fig.tight_layout()
    fig.savefig(OUT / "event_study_pooled.png", dpi=200)
    plt.close(fig)

    # Per-state paths for adult markers and total
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharex=True)
    cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"]
    for ax, y in zip(axes, ["adult_markers", "total"]):
        tp = paths[y][0]
        for c, s in zip(cols, TREATED):
            ax.plot(tp.index, tp[s], color=c, lw=1.6, label=f"{s} ({TREATED[s]})")
        ax.axvline(-0.5, color=muted, lw=1, ls="--")
        ax.axhline(0, color=muted, lw=0.8)
        ax.set_title(OUTCOMES[y], fontsize=10, loc="left", color=ink)
        ax.set_xlabel("Months since adult benefit start", fontsize=9, color=muted)
        ax.tick_params(colors=muted, labelsize=8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("log gap vs controls", fontsize=8, color=muted)
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "event_study_by_state.png", dpi=200)
    plt.close(fig)


def main() -> None:
    panel = load()
    scr = screen_states(panel)
    scr.to_csv(OUT / "state_screen.csv")
    res, paths = estimates(panel)
    res.round(4).to_csv(OUT / "did_estimates.csv", index=False)
    plot(paths, res)
    pd.set_option("display.width", 200)
    print(res[["outcome", "state", "pct", "perm_p", "mde_pct"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
