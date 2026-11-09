# Adult Medicaid dental benefits and children's care: preliminary analysis

Research question: when a state adds adult Medicaid dental coverage, what happens to children's Medicaid dental care? Parents gaining coverage may bring children in more often (household spillover; Lipton 2021, JHE; Hill, Jones and Chi 2022, Med Care). Dentists who treat both age groups may also ration chair time toward newly covered adults (displacement). Buchmueller, Miller and Vujicic (AEJ: Policy 2016) found no crowding out of privately insured patients. Nobody has tested displacement of Medicaid children at the provider level across states.

## Reproduce

From a fresh clone, the category-level analysis needs no raw data:

```bash
python analysis/adult_dental_spillover/prelim.py
```

With the local merged claims file, build the code-level panel first. `prelim.py` then adds child and adult code outcomes automatically:

```bash
python analysis/adult_dental_spillover/build_code_panel.py --merged path/to/merged_hhs_nppes_geo.csv && python analysis/adult_dental_spillover/prelim.py
```

| File                              | Contents                                                                   |
| --------------------------------- | -------------------------------------------------------------------------- |
| `policy_events.csv`               | Every policy event used by the rules, with date and source                 |
| `design.py`                       | The four selection rules                                                   |
| `output/design_stacks.csv`        | Treated states, windows, controls, and the reason every other state is out |
| `output/did_estimates.csv`        | DiD by outcome and state, permutation p-values, minimum detectable effects |
| `output/did_sensitivity.csv`      | Pooled estimates under the two robustness checks                           |
| `output/falsification_flags.csv`  | Controls flagged by the falsification check                                |
| `output/event_study_category.png` | Pooled event studies, category outcomes                                    |
| `output/event_study_code.png`     | Pooled event studies, code-level outcomes (after `build_code_panel.py`)    |
| `output/code_panel_state.csv`     | State × month × age group × provider type (after `build_code_panel.py`)    |

## How states are selected

Four rules, applied the same way to every state. The design is a stacked difference-in-differences (Cengiz, Dube, Lindner and Zipperer 2019, QJE; Wing, Freedman and Hollingsworth 2024, NBER w32054). Each adopting state is its own sub-experiment, compared only with states that had no policy change in its window. That avoids comparing late adopters with early adopters, the bias Goodman-Bacon (2021) and Callaway and Sant'Anna (2021) document for two-way fixed effects.

1. **Policy events.** Every event is a row in `policy_events.csv` with a date and a source. An `adopt` event means the state began covering routine cleanings for all non-pregnant adults, with no such coverage before. Any other change to an adult dental benefit is `expand`. ACA Medicaid expansion is `aca`.
2. **Window.** Every sub-experiment covers 24 months before and 18 months after adoption. An adopter is treated only if its whole window fits inside the data (2018-01 to 2024-09).
3. **Clean window.** No state in a sub-experiment, treated or control, may have a policy event inside the window, apart from the treated state's own adoption.
4. **Usable data.** No state in a sub-experiment may have, inside the window, a CMS DQ Atlas rating of "Unusable" for Claims Volume – OT or Procedure Codes – OT Professional. These are two of the three topics CMS uses to suppress state-months in its own Medicaid dental reporting; the third (enrollment) is not in our DQ file. No state may have a reporting break either, meaning average monthly dental claims changing more than 1.5× between consecutive half-years. The policy effect is about 1.15×, so this cannot select on treatment.

There are two robustness checks, and neither is used in the main estimate. The first is strict data quality, which also drops DQ Atlas "High concern". The second drops controls whose adult-marker share of claims rises 3× or more within the window, a sign of a policy change missing from the events file.

### What the rules produce

| Treated | Adoption | Controls |
| ------- | -------- | -------: |
| VA      | 2021-07  |       36 |
| ME      | 2022-07  |       26 |
| MD      | 2023-01  |       27 |
| TN      | 2023-01  |       27 |
| HI      | 2023-01  |       27 |
| NH      | 2023-04  |       26 |

Five adopters are excluded, each by a rule. DE and WV have reporting breaks (rule 4). OK expanded Medicaid the same month it adopted, and KS added dentures 12 months after adopting (rule 3). GA's window runs past the data (rule 2). The DQ Atlas part of rule 4 removes only UT 2018–2020. Texas's roughly 14× jump in 2020–21 is not flagged there, which is why the reporting-break test exists. `output/design_stacks.csv` lists the reason for every state left out of every sub-experiment.

Dates come from state agency documents for HI (SPA 22-0012) and OK (SPA OK-21-0029). The rest come from secondary sources (CareQuest, KFF budget surveys, CHCS). Before submission, replace each with the state plan amendment or agency notice.

## Estimation

Every outcome uses one scale: monthly claims per 100 of the state's own average monthly dental claims in the 24 pre-adoption months. Adult and child changes are therefore in the same units, and zero counts need no special handling. `pct_of_baseline` in the outputs restates each estimate as a percent of that outcome's own pre-adoption level in the treated states.

Each sub-experiment's estimate is a 2×2 DiD (post minus pre gap between the treated state and the mean of its controls). The pooled estimate is the equal-weight mean across sub-experiments. COVID shutdown months (March to June 2020) are dropped from every calculation: outcomes, baselines, the reporting-break test and the falsification check. The panel ends 2024-09 to avoid the late-2024 claims lag (LIMITATIONS L02).

Inference is by permutation, the standard approach with few treated units (Conley and Taber 2011; MacKinnon and Webb 2020). Each control is re-run as a placebo against the other controls in its sub-experiment. The pooled p-value comes from 5,000 draws that assign one placebo state to each sub-experiment, never the same state twice in a draw. The minimum detectable effect (MDE) is 2.8 × the placebo SD (80% power, two-sided 5%).

When the code-level panel is present, `prelim.py` first checks that its state-month totals equal the shipped category totals exactly (both come from the same merged file) and stops if they do not.

## Results

Units are claims per 100 baseline dental claims.

| Outcome                                         | Pooled DiD | % of own baseline | Permutation p |   MDE |
| ----------------------------------------------- | ---------: | ----------------: | ------------: | ----: |
| All dental claims                               |      +15.0 |              +15% |       < 0.001 |  ±8.6 |
| Preventive + diagnostic                         |      +11.8 |              +15% |       < 0.001 |  ±6.9 |
| Adult-marker categories (perio, prosthodontics) |      +0.37 |             +222% |       < 0.001 | ±0.26 |
| Orthodontics                                    |      −0.05 |               −4% |          0.62 | ±0.30 |

By state, total claims rose 31.7 in MD, 17.0 in ME, 15.7 in HI, 15.4 in VA and 12.4 in TN. NH fell 2.1. The pooled total is +15.6 with strict data quality and +14.4 with flagged controls dropped.

The first code-level run on the full merged file (1,215.5M claims, reconciling exactly with the category totals) gave child-marker codes +1.08 (p = 0.14, MDE ±2.1), general dentists −0.30 (p = 0.49), pediatric dentists +0.43 (p = 0.28), adult-marker codes +0.36 (p < 0.001) and D1110 +1.89 (p < 0.001). That run predates the COVID-baseline and placebo-draw fixes, so rerun before quoting.

## What this means for the paper

1. Adults came in. Adult-marker categories and codes rise within three months of each start date and stay up. Small-cell suppression hides most low-volume adult procedures, so treat their size as a lower bound.
2. Total dental volume rises about 15% of baseline.
3. Children's care did not fall. Child-marker codes moved up, not down, and the estimate rules out a drop larger than about 2% of children's volume. The rise itself is not statistically reliable.
4. The general-dentist dip and pediatric-dentist rise point the way displacement would, but neither is reliable and the gap has not been tested directly. The provider panel (`output/code_panel_provider.parquet`) is where to test it.
5. NH needs a closer look. Adult-marker claims rise in the months before its April 2023 date, and total claims do not move.

## Next steps

1. Rerun `build_code_panel.py` and `prelim.py`, and commit `output/code_panel_state.csv` (never the parquet).
2. Test the general-versus-pediatric gap directly, with heterogeneity by county dentist supply.
3. Benchmark Virginia's code-level adult volume against DMAS published adult dental utilization to measure how much small-cell suppression hides.
4. Add CMS monthly Medicaid enrollment for adults and children (data.medicaid.gov). The 2023 adoptions overlap the start of unwinding.
5. Collect child fee-schedule changes around each adoption date, and verify every date in `policy_events.csv` against primary sources.

## Limitations

Category outcomes mix children and adults; only the code-level outcomes separate them. Geography comes from the provider's practice address. The policy events file can miss changes. The falsification check is there to catch those, and it flags SC and UT in most sub-experiments (results barely move when they are dropped). See [`docs/LIMITATIONS.md`](../../docs/LIMITATIONS.md) for the full data ledger.
