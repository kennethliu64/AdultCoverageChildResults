"""Rules that pick treated states and controls. Same rules for every state.

Design: stacked difference-in-differences (Cengiz, Dube, Lindner and
Zipperer 2019, QJE; Wing, Freedman and Hollingsworth 2024, NBER w32054).
Each adopting state is one sub-experiment ("stack") with a fixed window,
compared only with states that had no policy change in that window.

Rule 1  Policy events. Every event is a row in policy_events.csv with a date
        and a source.
          adopt  = state begins covering routine cleanings for all
                   non-pregnant adults (no such coverage before)
          expand = any other change to an existing adult dental benefit
          aca    = ACA Medicaid expansion
Rule 2  Window. Every stack covers 24 months before and 18 months after the
        adoption month. An adopter is treated only if its whole window falls
        inside the data (2018-01 to 2024-09).
Rule 3  Clean window. No state in a stack, treated or control, may have a
        policy event inside the window, apart from the treated state's own
        adoption.
Rule 4  Usable data. No state in a stack may have, inside the window,
        (a) a CMS DQ Atlas rating of "Unusable" for Claims Volume - OT or
            Procedure Codes - OT Professional (two of the three topics CMS
            uses to suppress state-months in its own Medicaid dental
            reporting; the third, enrollment, is not in our DQ file), or
        (b) a reporting break: average monthly dental claims changing by
            more than 1.5x between consecutive half-years. The policy effect
            is about 1.15x, so this cannot select on treatment.

COVID: the shutdown months (COVID_MONTHS) are dropped everywhere: outcomes,
baselines, the reporting-break test and the falsification check.

Robustness checks (never used in the main estimate):
  - strict data quality: Rule 4a also drops "High concern"
  - falsification: drop controls whose adult-marker share of claims rises
    3x or more within the window, a sign of a policy change missing from
    policy_events.csv
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
PRE, POST = 24, 18
COVID_MONTHS = ("2020-03", "2020-06")  # inclusive; dropped from every calculation
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


def drop_covid(df: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """Remove the COVID shutdown months (index is 'YYYY-MM')."""
    keep = (df.index < COVID_MONTHS[0]) | (df.index > COVID_MONTHS[1])
    return df[keep]


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


def load_events() -> pd.DataFrame:
    return pd.read_csv(HERE / "policy_events.csv", dtype=str)


def _events_in_window(ev: pd.DataFrame, state: str, lo: str, hi: str, own: tuple[str, str] | None) -> str | None:
    """Rule 3."""
    e = ev[(ev.state == state) & (ev.effective >= lo) & (ev.effective <= hi)]
    if own:
        e = e[~((e.event == own[0]) & (e.effective == own[1]))]
    return ("policy event in window: " + ", ".join(e.event + " " + e.effective)) if len(e) else None


def _dq(dq: dict, state: str, lo: str, hi: str, strict: bool) -> str | None:
    """Rule 4a."""
    bad = {"Unusable", "High concern"} if strict else {"Unusable"}
    for y in range(int(lo[:4]), int(hi[:4]) + 1):
        for t in DQ_TOPICS:
            a = dq[t]["years"].get(str(y), {}).get(state, {}).get("assessment")
            if a in bad:
                return f"DQ Atlas {t} {y}: {a}"
    return None


def _break(total: pd.DataFrame, state: str, lo: str, hi: str) -> str | None:
    """Rule 4b."""
    if state not in total.columns:
        return "no data"
    s = drop_covid(total[state].loc[lo:hi])
    p = pd.PeriodIndex(s.index, freq="M")
    half = s.groupby([f"{x.year}H{1 if x.month <= 6 else 2}" for x in p]).mean()
    if (half <= 0).any():
        return "reporting break (zero claims)"
    r = np.exp(np.abs(np.diff(np.log(half.values)))).max(initial=1.0)
    return f"reporting break (half-year ratio {r:.2f})" if r > BREAK_RATIO else None


def build(total: pd.DataFrame, strict_dq: bool = False) -> Design:
    """total: month x state frame of total dental claims, index 'YYYY-MM'."""
    ev = load_events()
    dq = json.loads((ROOT / "public/data/dq_atlas.json").read_text())["topics"]
    total = total.reindex(columns=STATES).fillna(0)
    stacks, excluded = [], {}
    for _, a in ev[ev.event == "adopt"].sort_values("effective").iterrows():
        s, d = a.state, a.effective
        lo, hi = ym(d, -PRE), ym(d, POST - 1)
        if lo < START or hi > END:  # Rule 2
            excluded[s] = f"window {lo}..{hi} outside data {START}..{END}"
            continue
        reason = (
            _events_in_window(ev, s, lo, hi, own=("adopt", d))
            or _dq(dq, s, lo, hi, strict_dq)
            or _break(total, s, lo, hi)
        )
        if reason:
            excluded[s] = reason
            continue
        st = Stack(s, d, lo, hi)
        for c in STATES:
            if c == s:
                continue
            reason = _events_in_window(ev, c, lo, hi, own=None) or _dq(dq, c, lo, hi, strict_dq) or _break(total, c, lo, hi)
            if reason:
                st.dropped[c] = reason
            else:
                st.controls.append(c)
        stacks.append(st)
    return Design(stacks, excluded)


def falsification_flags(adult: pd.DataFrame, total: pd.DataFrame, st: Stack) -> list[str]:
    """Robustness: controls whose adult-marker share rises FALSIFY_RATIO-fold or more."""
    adult, total = drop_covid(adult), drop_covid(total)
    pre_end = ym(st.adopt, -1)
    flags = []
    for c in st.controls:
        pre = adult.loc[st.lo : pre_end, c].sum() / max(total.loc[st.lo : pre_end, c].sum(), 1)
        post = adult.loc[st.adopt : st.hi, c].sum() / max(total.loc[st.adopt : st.hi, c].sum(), 1)
        if post >= FALSIFY_RATIO * max(pre, 1e-4):
            flags.append(c)
    return flags


def describe(design: Design) -> pd.DataFrame:
    rows = [
        {
            "treated": st.state,
            "adopt": st.adopt,
            "window": f"{st.lo}..{st.hi}",
            "n_controls": len(st.controls),
            "controls": " ".join(st.controls),
            "dropped": "; ".join(f"{k}: {v}" for k, v in sorted(st.dropped.items())),
        }
        for st in design.stacks
    ]
    rows += [
        {"treated": s, "adopt": "", "window": "", "n_controls": 0, "controls": "", "dropped": f"EXCLUDED: {r}"}
        for s, r in design.excluded_treated.items()
    ]
    return pd.DataFrame(rows)
