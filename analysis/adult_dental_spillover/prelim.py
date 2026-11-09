"""Adult Medicaid dental benefit adoption and children's dental care.

Stacked DiD. Treated states and controls come only from the rules in
design.py. Every outcome uses one scale: monthly claims per 100 of the
state's own average monthly dental claims in the 24 pre-adoption months.
So +5 on any outcome means "5% of the state's baseline dental volume",
which puts adult and child changes in the same units and handles zero
counts without special cases.

    python analysis/adult_dental_spillover/prelim.py

Category outcomes come from the shipped monthly state file. If
output/code_panel_state.csv exists (from build_code_panel.py), code-level
child and adult outcomes are added.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import design as D

SRC = D.ROOT / "public/data/provider_procedure_category_aggregate_monthly_state.json"
CODE_PANEL = D.HERE / "output" / "code_panel_state.csv"
OUT = D.HERE / "output"
OUT.mkdir(exist_ok=True)
RNG = np.random.default_rng(20261109)
N_DRAWS = 5000
UNIT = "claims per 100 baseline dental claims"

ADULT_CATS = ["Periodontics", "Prosthodontics (removable)", "Prosthodontics (fixed)", "Implant Services"]
LABELS = {
    "total": "All dental claims",
    "adult_markers": "Adult-marker categories (perio, prosthodontics, implants)",
    "prev_diag": "Preventive + diagnostic",
    "ortho": "Orthodontics",
    "code_child": "Child-marker codes, all dentists",
    "code_child_general": "Child-marker codes, general dentists",
    "code_child_pediatric": "Child-marker codes, pediatric dentists",
    "code_adult": "Adult-marker codes, all dentists",
    "code_teen_adult": "D1110 (age 14+ prophylaxis)",
}


def _wide(df: pd.DataFrame) -> pd.DataFrame:
    w = df.pivot_table(index="ym", columns="state", values="claims", aggfunc="sum")
    w = w.reindex(columns=D.STATES).fillna(0)
    return w[(w.index >= D.START) & (w.index <= D.END)]


def load_category() -> dict[str, pd.DataFrame]:
    rows = []
    with SRC.open() as f:
        for line in f:
            for st, recs in json.loads(line).items():
                rows += [(st, r["year_month"], r["category"], r["total_claims"]) for r in recs]
    df = pd.DataFrame(rows, columns=["state", "ym", "cat", "claims"])
    return {
        "total": _wide(df),
        "adult_markers": _wide(df[df.cat.isin(ADULT_CATS)]),
        "prev_diag": _wide(df[df.cat.isin(["Preventive", "Diagnostic"])]),
        "ortho": _wide(df[df.cat == "Orthodontics"]),
    }


def load_code(category_total: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not CODE_PANEL.exists():
        return {}
    c = pd.read_csv(CODE_PANEL, dtype={"ym": str})
    # Both panels come from the same merged file, so totals must match exactly.
    diff = (_wide(c) - category_total).abs().values.max()
    if diff > 1:
        raise SystemExit(f"code panel and category totals disagree by up to {diff:,.0f} claims in a state-month")
    child = c.age_group == "child"
    return {
        "code_child": _wide(c[child]),
        "code_child_general": _wide(c[child & (c.prov_type == "general")]),
        "code_child_pediatric": _wide(c[child & (c.prov_type == "pediatric")]),
        "code_adult": _wide(c[c.age_group == "adult"]),
        "code_teen_adult": _wide(c[c.age_group == "teen_adult"]),
    }


def scaled(raw: pd.DataFrame, total: pd.DataFrame, st: D.Stack, states: list[str]) -> pd.DataFrame:
    base = D.drop_covid(total.loc[st.lo : D.ym(st.adopt, -1), states]).mean()
    y = D.drop_covid(raw.reindex(index=total.index, fill_value=0).loc[st.lo : st.hi, states]) / base * 100
    y.index = [(pd.Period(m, "M") - pd.Period(st.adopt, "M")).n for m in y.index]  # event time
    return y


def gap(y: pd.DataFrame, s: str, ctl: list[str]) -> pd.Series:
    return y[s] - y[ctl].mean(axis=1)


def did(y: pd.DataFrame, s: str, ctl: list[str]) -> float:
    g = gap(y, s, ctl)
    return g[g.index >= 0].mean() - g[g.index < 0].mean()


def estimate(raw, total, design, drop=None):
    per, plac, paths, cpaths, base = {}, {}, {}, {}, {}
    for st in design.stacks:
        ctl = [c for c in st.controls if c not in (drop or {}).get(st.state, [])]
        y = scaled(raw, total, st, [st.state] + ctl)
        per[st.state] = did(y, st.state, ctl)
        base[st.state] = y.loc[y.index < 0, st.state].mean()  # outcome's own baseline, same units
        plac[st.state] = {c: did(y, c, [x for x in ctl if x != c]) for c in ctl}
        g = gap(y, st.state, ctl)
        paths[st.state] = g - g.loc[-12:-1].mean()
        cp = {}
        for c in ctl:
            gc = gap(y, c, [x for x in ctl if x != c])
            cp[c] = gc - gc.loc[-12:-1].mean()
        cpaths[st.state] = cp

    def placebo_draw() -> dict[str, str]:
        """One pseudo-treated control per stack, never the same state twice in a draw."""
        used, pick = set(), {}
        for s in per:
            options = [c for c in plac[s] if c not in used] or list(plac[s])
            pick[s] = options[RNG.integers(len(options))]
            used.add(pick[s])
        return pick

    rows = []
    for s, e in per.items():
        v = np.array(list(plac[s].values()))
        rows.append(dict(state=s, n_controls=len(v), did=e, baseline=base[s],
                         perm_p=(1 + (np.abs(v) >= abs(e)).sum()) / (1 + len(v)), placebo_sd=v.std(ddof=1)))  # fmt: skip
    picks = [placebo_draw() for _ in range(N_DRAWS)]
    pooled = np.mean(list(per.values()))
    draws = np.array([np.mean([plac[s][c] for s, c in p.items()]) for p in picks])
    rows.append(dict(state="POOLED", n_controls=np.nan, did=pooled, baseline=np.mean(list(base.values())),
                     perm_p=(1 + (np.abs(draws) >= abs(pooled)).sum()) / (1 + N_DRAWS), placebo_sd=draws.std(ddof=1)))  # fmt: skip
    res = pd.DataFrame(rows)
    res["mde"] = 2.8 * res.placebo_sd  # 80% power, two-sided 5%
    res["pct_of_baseline"] = 100 * res.did / res.baseline  # change relative to the outcome's own pre level
    tp = pd.concat(paths, axis=1)
    band = pd.concat([pd.concat([cpaths[s][c] for s, c in p.items()], axis=1).mean(axis=1) for p in picks[:1000]], axis=1)
    return res, (tp, band.quantile(0.05, axis=1), band.quantile(0.95, axis=1))


def plot(bands: dict, res: pd.DataFrame, keys: list[str], fname: str) -> None:
    keys = [k for k in keys if k in bands]
    if not keys:
        return
    ink, muted, grid, s1 = "#0b0b0b", "#52514e", "#e6e5e1", "#2a78d6"
    nrow = int(np.ceil(len(keys) / 2))
    fig, axes = plt.subplots(nrow, 2, figsize=(11, 3.7 * nrow), squeeze=False)
    for ax, y in zip(axes.flat, keys):
        tp, lo, hi = bands[y]
        x = tp.index.values
        ax.fill_between(x, lo.values, hi.values, color=grid, lw=0, label="Placebo 90% band")
        ax.plot(x, tp.mean(axis=1).values, color=s1, lw=2, label=f"Mean of {tp.shape[1]} adopting states")
        ax.axvline(-0.5, color=muted, lw=1, ls="--")
        ax.axhline(0, color=muted, lw=0.8)
        r = res[(res.outcome == y) & (res.state == "POOLED")].iloc[0]
        ax.set_title(f"{LABELS[y]}\npooled {r.did:+.2f}, p={r.perm_p:.3f}, MDE ±{r.mde:.2f}", fontsize=9.5, color=ink, loc="left")
        ax.tick_params(colors=muted, labelsize=8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.set_ylabel(UNIT, fontsize=7.5, color=muted)
        ax.set_xlabel("Months since adult benefit start", fontsize=8, color=muted)
    for ax in list(axes.flat)[len(keys) :]:
        ax.set_visible(False)
    axes[0, 0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=200)
    plt.close(fig)


def main() -> None:
    outcomes = load_category()
    outcomes.update(load_code(outcomes["total"]))
    total = outcomes["total"]
    design = D.build(total)
    strict = D.build(total, strict_dq=True)
    flags = {st.state: D.falsification_flags(outcomes["adult_markers"], total, st) for st in design.stacks}
    D.describe(design).to_csv(OUT / "design_stacks.csv", index=False)
    pd.Series({k: " ".join(v) for k, v in flags.items()}).to_csv(OUT / "falsification_flags.csv", header=["flagged_controls"])

    main_res, sens, bands = [], [], {}
    for y, raw in outcomes.items():
        r, bands[y] = estimate(raw, total, design)
        main_res.append(r.assign(outcome=y))
        for name, kw in [("strict_dq", dict(design=strict)), ("drop_falsification_flags", dict(design=design, drop=flags))]:
            rs, _ = estimate(raw, total, **kw)
            sens.append(rs[rs.state == "POOLED"].assign(outcome=y, spec=name))
    cols = ["outcome", "state", "n_controls", "baseline", "did", "pct_of_baseline", "perm_p", "placebo_sd", "mde"]
    res = pd.concat(main_res, ignore_index=True)[cols]
    res.round(4).to_csv(OUT / "did_estimates.csv", index=False)
    s = pd.concat(sens, ignore_index=True)[["outcome", "spec", "did", "pct_of_baseline", "perm_p", "mde"]]
    s.round(4).to_csv(OUT / "did_sensitivity.csv", index=False)

    plot(bands, res, ["total", "adult_markers", "prev_diag", "ortho"], "event_study_category.png")
    plot(bands, res, [k for k in LABELS if k.startswith("code_")], "event_study_code.png")

    pd.set_option("display.width", 200)
    print(D.describe(design)[["treated", "adopt", "n_controls", "dropped"]].to_string(index=False, max_colwidth=80))
    print(f"\nPooled DiD, {UNIT}")
    print(res[res.state == "POOLED"][["outcome", "baseline", "did", "pct_of_baseline", "perm_p", "mde"]].round(3).to_string(index=False))
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
