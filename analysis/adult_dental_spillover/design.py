"""Pre-specified rules that pick treated states and clean controls.

Every selection decision in the analysis comes from this module, applied the
same way to every state. No state is hand-picked. The rules follow the
stacked difference-in-differences design (Cengiz, Dube, Lindner and Zipperer
2019, QJE; Wing, Freedman and Hollingsworth 2024, NBER w32054): one
sub-experiment per adopting state, compared only with states that have no
policy change anywhere in that sub-experiment's window.

R1  Policy coding. Every documented adult-dental or ACA-expansion event is in
    policy_events.csv with a date and a source. Events have three types:
    adopt  = first coverage of routine preventive and restorative care for
             non-pregnant adults (prior benefit none, emergency-only, or
             without routine cleanings)
    expand = change in an existing adult benefit (caps, added services)
    aca    = ACA Medicaid expansion
R2  Treated. A state is treated if it has an `adopt` event with at least
    PRE months of data before it and at least MIN_POST months before END.
R3  Treated exclusion. Drop an adopter whose ACA expansion falls within
    ACA_GAP months of its adoption, since the two effects cannot be
    separated.
R4  Clean controls. For each treated state's window [d - PRE, d + POST - 1],
    a control has no event of any type inside the window and is not itself
    treated in the window.
R5  Data quality (CMS rule). Drop a state from a stack if any calendar year
    in the window is rated "Unusable" in the DQ Atlas for Claims Volume - OT
    or Procedure Codes - OT Professional. CMS uses this rule for its own
    Medicaid dental-services reporting. Sensitivity: also drop "High
    concern".
R6  Reporting breaks. Drop a state from a stack if average monthly total
    dental claims in any half-year of the window differ from the previous
    half-year by more than a factor of BREAK_RATIO (2020H1 skipped for the COVID shutdown). The
    threshold is far above any plausible policy effect, so the rule cannot
    select on treatment.
R8  Outcome volume. For each outcome other than the first-stage check, a
    state (treated or control) enters only if it averages at least
    MIN_VOLUME claims a month for that outcome in the pre-window, so log
    outcomes are not driven by near-zero counts.
R7  Falsification (reported, never used for selection in the main model).
    Flag controls whose adult-marker share of claims rises more than
    FALSIFY_RATIO-fold from the pre to the post part of the window. A flag suggests an undocumented
    policy change. Sensitivity: drop flagged controls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

START, END = "2018-01", "2024-09"  # END drops the Nov/Dec 2024 claims lag (LIMITATIONS L02)
PRE, POST, MIN_POST = 24, 18, 12
ACA_GAP = 12
MIN_VOLUME = 100  # R8: mean monthly pre-window claims an outcome needs, per state
BREAK_RATIO = 1.5
DQ_TOPICS = ("claims-volume", "proc-cd-prof")
FALSIFY_RATIO = 3.0

# 50 states + DC. Territories have no comparable policy coding.
STATES = (
    "AK AL AR AZ CA CO CT DC DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH "
    "NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY"
).split()


def ym(d: str, k: int = 0) -> str:
    return (pd.Period(d, "M") + k).strftime("%Y-%m")


def load_events() -> pd.DataFrame:
    return pd.read_csv(HERE / "policy_events.csv", dtype=str)


def load_dq() -> dict:
    return json.loads((ROOT / "public/data/dq_atlas.json").read_text())["topics"]


@dataclass
class Stack:
    state: str
    adopt: str
    lo: str
    hi: str
    controls: list[str] = field(default_factory=list)
    dropped: dict[str, str] = field(default_factory=dict)  # state -> reason


@dataclass
class Design:
    stacks: list[Stack]
    excluded_treated: dict[str, str]


def _dq_bad(dq: dict, state: str, lo: str, hi: str, strict: bool) -> str | None:
    bad = {"Unusable", "High concern"} if strict else {"Unusable"}
    for y in range(int(lo[:4]), int(hi[:4]) + 1):
        for t in DQ_TOPICS:
            a = dq[t]["years"].get(str(y), {}).get(state, {}).get("assessment")
            if a in bad:
                return f"DQ Atlas {t} {y}: {a}"
    return None


def _break(total: pd.Series, lo: str, hi: str) -> str | None:
    s = total.loc[lo:hi]
    if s.empty:
        return "no data"
    idx = pd.PeriodIndex(s.index, freq="M")
    half = pd.Series(s.values, index=[f"{p.year}H{1 if p.month <= 6 else 2}" for p in idx]).groupby(level=0).mean()  # monthly mean, so partial halves compare fairly
    half = half[half.index != "2020H1"]  # COVID shutdown half only
    r = np.exp(np.abs(np.diff(np.log(half.replace(0, np.nan).values))))
    if np.nanmax(r, initial=1) > BREAK_RATIO or np.isnan(r).any():
        return f"reporting break (max half-year ratio {np.nanmax(r, initial=1):.2f})"
    return None


def build(total_claims: pd.DataFrame, strict_dq: bool = False) -> Design:
    """total_claims: month x state frame of total dental claims (index 'YYYY-MM')."""
    ev = load_events()
    dq = load_dq()
    adopt = ev[ev.event == "adopt"].set_index("state").effective
    aca = ev[ev.event == "aca"].set_index("state").effective
    stacks, excl = [], {}
    for s, d in sorted(adopt.items(), key=lambda kv: kv[1]):
        lo, hi = ym(d, -PRE), min(ym(d, POST - 1), END)
        if lo < START:
            excl[s] = f"fewer than {PRE} pre months"
            continue
        if (pd.Period(END, "M") - pd.Period(d, "M")).n + 1 < MIN_POST:
            excl[s] = f"fewer than {MIN_POST} post months"
            continue
        if s in aca and abs((pd.Period(aca[s], "M") - pd.Period(d, "M")).n) <= ACA_GAP:
            excl[s] = f"ACA expansion {aca[s]} within {ACA_GAP} months of adoption"
            continue
        st = Stack(s, d, lo, hi)
        for who in [s] + [x for x in STATES if x != s]:
            reason = None
            if who != s:
                inwin = ev[(ev.state == who) & (ev.effective >= lo) & (ev.effective <= hi)]
                if len(inwin):
                    reason = "policy event in window: " + ", ".join(inwin.event + " " + inwin.effective)
            reason = reason or _dq_bad(dq, who, lo, hi, strict_dq)
            if reason is None:
                if who not in total_claims.columns:
                    reason = "no data"
                else:
                    reason = _break(total_claims[who], lo, hi)
            if who == s and reason:
                excl[s] = reason
                st = None
                break
            if reason:
                st.dropped[who] = reason
            elif who != s:
                st.controls.append(who)
        if st is not None:
            stacks.append(st)
    return Design(stacks, excl)


def falsification_flags(adult: pd.DataFrame, total: pd.DataFrame, stack: Stack) -> list[str]:
    """R7: controls whose adult-marker share jumps > FALSIFY_RATIO across the window."""
    flags = []
    for c in stack.controls:
        pre = adult.loc[stack.lo : ym(stack.adopt, -1), c].sum() / max(total.loc[stack.lo : ym(stack.adopt, -1), c].sum(), 1)
        post = adult.loc[stack.adopt : stack.hi, c].sum() / max(total.loc[stack.adopt : stack.hi, c].sum(), 1)
        if pre > 0 and post / pre > FALSIFY_RATIO or pre == 0 and post > 0.001:
            flags.append(c)
    return flags


def describe(design: Design) -> pd.DataFrame:
    rows = []
    for st in design.stacks:
        rows.append(
            {
                "treated": st.state,
                "adopt": st.adopt,
                "window": f"{st.lo}..{st.hi}",
                "n_controls": len(st.controls),
                "controls": " ".join(st.controls),
                "dropped": "; ".join(f"{k}: {v}" for k, v in sorted(st.dropped.items())),
            }
        )
    for s, r in design.excluded_treated.items():
        rows.append({"treated": s, "adopt": "", "window": "", "n_controls": 0, "controls": "", "dropped": f"EXCLUDED: {r}"})
    return pd.DataFrame(rows)
