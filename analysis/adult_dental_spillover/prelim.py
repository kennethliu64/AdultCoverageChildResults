"""Adult Medicaid dental benefit adoption and children's dental care.

Stacked DiD: one sub-experiment per adopting state, each compared with its
own clean controls. Treated and control states come only from the
pre-specified rules in design.py.

    python analysis/adult_dental_spillover/prelim.py

Category-level outcomes come from the shipped monthly state file. If
output/code_panel_state.csv exists (built by build_code_panel.py from the
local merged claims file), code-level child and adult outcomes are added.
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
COVID = ("2020-03", "2020-06")  # dropped from estimation
RNG = np.random.default_rng(20261109)
N_DRAWS = 5000
FIRST_STAGE = {"adult_markers", "code_adult"}  # exempt from the R8 volume rule

ADULT_CATS = ["Periodontics", "Prosthodontics (removable)", "Prosthodontics (fixed)", "Implant Services"]
LABELS = {
    "adult_markers": "Adult-marker categories (perio, prosthodontics, implants)",
    "total": "All dental claims",
    "prev_diag": "Preventive + diagnostic claims",
    "ortho": "Orthodontic claims",
    "code_child": "Child-marker codes, all dentists",
    "code_child_general": "Child-marker codes, general dentists",
    "code_child_pediatric": "Child-marker codes, pediatric dentists",
    "code_adult": "Adult-marker codes, all dentists",
    "code_teen_adult": "D1110 (age 14+ prophylaxis)",
}


def load_category() -> pd.DataFrame:
    rows = []
    with SRC.open() as f:
        for line in f:
            for st, recs in json.loads(line).items():
                for r in recs:
                    rows.append((st, r["year_month"], r["category"], r["total_claims"]))
    df = pd.DataFrame(rows, columns=["state", "ym", "cat", "claims"])
    df = df[(df.ym >= D.START) & (df.ym <= D.END) & df.state.isin(D.STATES)]
    out = {
        "total": df,
        "adult_markers": df[df.cat.isin(ADULT_CATS)],
        "prev_diag": df[df.cat.isin(["Preventive", "Diagnostic"])],
        "ortho": df[df.cat == "Orthodontics"],
    }
    return {k: v.pivot_table(index="ym", columns="state", values="claims", aggfunc="sum") for k, v in out.items()}


def load_code() -> dict[str, pd.DataFrame]:
    if not CODE_PANEL.exists():
        return {}
    c = pd.read_csv(CODE_PANEL, dtype={"ym": str})
    c = c[(c.ym >= D.START) & (c.ym <= D.END) & c.state.isin(D.STATES)]

    def wide(mask):
        return c[mask].pivot_table(index="ym", columns="state", values="claims", aggfunc="sum")

    return {
        "code_child": wide(c.age_group == "child"),
        "code_child_general": wide((c.age_group == "child") & (c.prov_type == "general")),
        "code_child_pediatric": wide((c.age_group == "child") & (c.prov_type == "pediatric")),
        "code_adult": wide(c.age_group == "adult"),
        "code_teen_adult": wide(c.age_group == "teen_adult"),
    }


def logw(w: pd.DataFrame) -> pd.DataFrame:
    w = w.reindex(columns=D.STATES).fillna(0)
    w = np.log1p(w)
    w.loc[(w.index >= COVID[0]) & (w.index <= COVID[1])] = np.nan
    return w


def eligible(raw: pd.DataFrame, y: str, st: D.Stack, states: list[str]) -> list[str]:
    if y in FIRST_STAGE:
        return states
    pre = raw.reindex(columns=D.STATES).fillna(0).loc[st.lo : D.ym(st.adopt, -1)]
    return [s for s in states if pre[s].mean() >= D.MIN_VOLUME]


def did(w: pd.DataFrame, s: str, st: D.Stack, ctl: list[str]) -> float:
    pre = w.loc[st.lo : D.ym(st.adopt, -1)]
    post = w.loc[st.adopt : st.hi]
    return (post[s] - post[ctl].mean(axis=1)).mean() - (pre[s] - pre[ctl].mean(axis=1)).mean()


def path(w: pd.DataFrame, s: str, st: D.Stack, ctl: list[str]) -> pd.Series:
    ks = range(-D.PRE, (pd.Period(st.hi, "M") - pd.Period(st.adopt, "M")).n + 1)
    g = pd.Series({k: w.loc[D.ym(st.adopt, k), s] - w.loc[D.ym(st.adopt, k), ctl].mean() for k in ks})
    return g - g.loc[-12:-1].mean()


def estimate(raw: pd.DataFrame, y: str, design: D.Design, drop: dict[str, list[str]] | None = None):
    w = logw(raw)
    per, plac, paths, cpaths = {}, {}, {}, {}
    for st in design.stacks:
        if not eligible(raw, y, st, [st.state]):
            continue
        ctl = [c for c in eligible(raw, y, st, st.controls) if c not in (drop or {}).get(st.state, [])]
        if len(ctl) < 5:
            continue
        per[st.state] = did(w, st.state, st, ctl)
        plac[st.state] = {c: did(w, c, st, [x for x in ctl if x != c]) for c in ctl}
        paths[st.state] = path(w, st.state, st, ctl)
        cpaths[st.state] = {c: path(w, c, st, [x for x in ctl if x != c]) for c in ctl}
    rows = []
    for s, est in per.items():
        dist = np.array(list(plac[s].values()))
        rows.append(dict(outcome=y, state=s, n_controls=len(dist), did_log=est,
                         perm_p=(1 + (np.abs(dist) >= abs(est)).sum()) / (1 + len(dist)),
                         placebo_sd=dist.std(ddof=1)))  # fmt: skip
    if per:
        pooled = np.mean(list(per.values()))
        draws = np.array([np.mean([RNG.choice(list(plac[s].values())) for s in per]) for _ in range(N_DRAWS)])
        rows.append(dict(outcome=y, state="POOLED", n_controls=np.nan, did_log=pooled,
                         perm_p=(1 + (np.abs(draws) >= abs(pooled)).sum()) / (1 + N_DRAWS),
                         placebo_sd=draws.std(ddof=1)))  # fmt: skip
    res = pd.DataFrame(rows)
    if len(res):
        res["pct"] = 100 * (np.exp(res.did_log) - 1)
        res["mde_pct"] = 100 * (np.exp(2.8 * res.placebo_sd) - 1)
    band = None
    if paths:
        tp = pd.concat(paths, axis=1)
        b = []
        for _ in range(1000):
            b.append(pd.concat([cpaths[s][RNG.choice(list(cpaths[s]))] for s in paths], axis=1).mean(axis=1))
        band = (tp, pd.concat(b, axis=1).quantile(0.05, axis=1), pd.concat(b, axis=1).quantile(0.95, axis=1))
    return res, band


def plot(bands: dict, res: pd.DataFrame, keys: list[str], fname: str) -> None:
    keys = [k for k in keys if bands.get(k) is not None]
    if not keys:
        return
    ink, muted, grid, s1 = "#0b0b0b", "#52514e", "#e6e5e1", "#2a78d6"
    n = len(keys)
    cols = 2
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(11, 3.7 * rows), squeeze=False)
    for ax, y in zip(axes.flat, keys):
        tp, lo, hi = bands[y]
        x = tp.index.values
        ax.fill_between(x, lo.reindex(x).values, hi.reindex(x).values, color=grid, lw=0, label="Placebo 90% band")
        ax.plot(x, tp.mean(axis=1).values, color=s1, lw=2, label=f"Mean of {tp.shape[1]} adopting states")
        ax.axvline(-0.5, color=muted, lw=1, ls="--")
        ax.axhline(0, color=muted, lw=0.8)
        r = res[(res.outcome == y) & (res.state == "POOLED")].iloc[0]
        ax.set_title(f"{LABELS[y]}\npooled {r.pct:+.1f}%, permutation p={r.perm_p:.3f}, MDE ±{r.mde_pct:.0f}%",
                     fontsize=9.5, color=ink, loc="left")  # fmt: skip
        ax.tick_params(colors=muted, labelsize=8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.set_ylabel("log gap vs clean controls", fontsize=8, color=muted)
        ax.set_xlabel("Months since adult benefit start", fontsize=8, color=muted)
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    axes[0, 0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=200)
    plt.close(fig)


def main() -> None:
    outcomes = load_category()
    outcomes.update(load_code())
    design = D.build(outcomes["total"])
    D.describe(design).to_csv(OUT / "design_stacks.csv", index=False)
    strict = D.build(outcomes["total"], strict_dq=True)
    flags = {st.state: D.falsification_flags(outcomes["adult_markers"].reindex(columns=D.STATES).fillna(0),
                                             outcomes["total"].reindex(columns=D.STATES).fillna(0), st)
             for st in design.stacks}  # fmt: skip

    main_res, sens, bands = [], [], {}
    for y, raw in outcomes.items():
        r, b = estimate(raw, y, design)
        main_res.append(r)
        bands[y] = b
        for name, kw in [("strict_dq", dict(design=strict)), ("drop_falsification_flags", dict(design=design, drop=flags))]:
            rs, _ = estimate(raw, y, **kw)
            sens.append(rs[rs.state == "POOLED"].assign(spec=name))
    res = pd.concat(main_res, ignore_index=True)
    res.round(4).to_csv(OUT / "did_estimates.csv", index=False)
    pd.concat(sens, ignore_index=True).round(4).to_csv(OUT / "did_sensitivity.csv", index=False)
    pd.Series({k: " ".join(v) for k, v in flags.items()}).to_csv(OUT / "falsification_flags.csv", header=["flagged_controls"])

    plot(bands, res, ["adult_markers", "total", "prev_diag", "ortho"], "event_study_category.png")
    plot(bands, res, [k for k in LABELS if k.startswith("code_")], "event_study_code.png")

    pd.set_option("display.width", 200)
    print(D.describe(design)[["treated", "adopt", "n_controls", "dropped"]].to_string(index=False, max_colwidth=90))
    print()
    print(res[res.state == "POOLED"][["outcome", "pct", "perm_p", "mde_pct"]].round(3).to_string(index=False))
    s = pd.concat(sens)
    print(s[["outcome", "spec", "pct", "perm_p"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
