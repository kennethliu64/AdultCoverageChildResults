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

| File                              | Contents                                                                        |
| --------------------------------- | ------------------------------------------------------------------------------- |
| `policy_events.csv`               | Every adult-dental and ACA-expansion event used for selection, with source      |
| `design.py`                       | The selection rules (R1–R8), applied identically to every state                 |
| `output/design_stacks.csv`        | Treated states, their windows, clean controls, and the reason for every drop    |
| `output/did_estimates.csv`        | DiD by outcome and state, permutation p-values, minimum detectable effects      |
| `output/did_sensitivity.csv`      | Pooled estimates under strict DQ screening and with falsification flags dropped |
| `output/falsification_flags.csv`  | Controls whose adult-marker share jumps (possible undocumented policy change)   |
| `output/event_study_category.png` | Pooled event studies, category outcomes                                         |
| `output/event_study_code.png`     | Pooled event studies, code-level outcomes (after `build_code_panel.py`)         |
| `output/code_panel_state.csv`     | State × month × age group × provider type (after `build_code_panel.py`)         |

## How states are selected

Every selection decision is a rule in `design.py`, applied the same way to all 50 states and DC. Nothing is hand-picked. The design is a stacked difference-in-differences (Cengiz, Dube, Lindner and Zipperer 2019, QJE; Wing, Freedman and Hollingsworth 2024, NBER w32054). Each adopting state is its own sub-experiment, compared only with states that had no policy change anywhere in that sub-experiment's window. This avoids the bias from comparing late adopters with early adopters in two-way fixed effects (Goodman-Bacon 2021; Callaway and Sant'Anna 2021).

| Rule | What it does                                                                                                                                                                                                                                                                        |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1   | Every documented adult-dental change and ACA expansion is listed in `policy_events.csv` with a date and source. `adopt` means first routine preventive and restorative coverage for non-pregnant adults. `expand` means a change to an existing benefit. `aca` means ACA expansion. |
| R2   | Treated = an `adopt` event with 24 months of data before it and at least 12 after (data run 2018-01 to 2024-09).                                                                                                                                                                    |
| R3   | Drop an adopter whose ACA expansion falls within 12 months of its adoption, since the two cannot be separated.                                                                                                                                                                      |
| R4   | Clean controls for a stack have no event of any type inside that stack's window.                                                                                                                                                                                                    |
| R5   | Drop any state-window rated "Unusable" in the CMS DQ Atlas for Claims Volume – OT or Procedure Codes – OT Professional. CMS applies this rule in its own Medicaid dental-services reporting. Sensitivity also drops "High concern".                                                 |
| R6   | Drop any state-window where average monthly dental claims change by more than 1.5× between consecutive half-years (COVID half 2020H1 skipped). The policy effect is about 1.1×, so this cannot select on treatment.                                                                 |
| R7   | Falsification, never used in the main model. Flag controls whose adult-marker share rises more than 3× across the window. Sensitivity drops them.                                                                                                                                   |
| R8   | For each outcome except the adult first-stage check, a state enters only if it averages 100+ claims a month on that outcome before adoption.                                                                                                                                        |

The rules give seven treated states. Each has 26 to 36 clean controls.

| Treated | Start   | Clean controls |
| ------- | ------- | -------------: |
| VA      | 2021-07 |             36 |
| ME      | 2022-07 |             26 |
| KS      | 2022-07 |             26 |
| MD      | 2023-01 |             27 |
| TN      | 2023-01 |             27 |
| HI      | 2023-01 |             27 |
| NH      | 2023-04 |             26 |

Four adopters are excluded by rule. DE (2020-10) and WV (2021-01) have reporting breaks in their windows (R6). OK (2021-07) adopted in the same month it expanded Medicaid (R3). GA (2024-07) has too little follow-up (R2). The DQ Atlas rule removes only UT 2018–2020. Texas's roughly 14× jump in 2020–21 is not flagged there, which is why R6 exists.

Dates are coded from state agency documents for HI (SPA 22-0012) and OK (SPA OK-21-0029). The rest come from secondary sources (CareQuest, KFF budget surveys, CHCS). Before submission, replace each secondary date with the state plan amendment or agency notice. Absence from `policy_events.csv` is not proof of no change. R7 exists to catch that, and it flags SC and UT in most stacks.

## Estimation

Outcome is log(1 + monthly claims). The window is 24 months before and up to 18 after each start date. March to June 2020 is dropped, and the panel ends 2024-09 to avoid the late-2024 claims lag (LIMITATIONS L02). Each stack's estimate is a 2×2 DiD against its clean-control mean. The pooled estimate is the equal-weight mean across stacks.

Inference is by permutation, the standard approach with few treated units (Conley and Taber 2011; MacKinnon and Webb 2020). Each clean control is re-run as a placebo against the other controls in its stack. The pooled p-value comes from 5,000 draws of one placebo per stack. The MDE is 2.8 × the placebo SD (80% power, two-sided 5%).

## Results (category level)

| Outcome                                                   | Pooled DiD | Permutation p | Pooled MDE |
| --------------------------------------------------------- | ---------: | ------------: | ---------: |
| Adult-marker categories (perio, prosthodontics, implants) |      +458% |       < 0.001 |      ±116% |
| All dental claims                                         |     +11.3% |         0.001 |      ±8.4% |
| Preventive + diagnostic claims                            |     +11.0% |         0.002 |      ±8.5% |
| Orthodontic claims                                        |     −18.2% |          0.26 |       ±68% |

Total claims rose 30% in MD, 15% in VA, ME and HI, and 12% in TN. KS (−4%) and NH (−2%) did not move. The pooled total is +11.9% with strict DQ screening and +10.5% with falsification-flagged controls dropped.

## What this means for the paper

1. The first stage is clear. Adult-marker claims rise within three months of each start date and stay up.
2. The adult inflow is modest. If children's volume were unchanged, adults add about 11% to claim volume in the first 18 months.
3. A state-level design cannot detect displacement. The pooled MDE is about 8%. Displacement that large would mean children lost most of the adult inflow. A plausible effect (a quarter of the inflow, about 3%) is below detection.
4. The child question has to be answered within states at the provider level. Compare children's claims at general dentists (who absorb new adults) with children's claims at pediatric dentists (taxonomy 1223P0221X, who mostly do not), using `output/code_panel_provider.parquet`. Add heterogeneity by each dentist's pre-period Medicaid volume and by county dentist supply.
5. KS and NH need a closer look. Both adopted, both show a first stage, and neither shows any rise in total claims. Possible causes are a wrong date, adult claims routed through a channel this data misses, or real displacement.

## Next steps

1. Run `build_code_panel.py` on the merged file. It splits claims into child-marker codes (D0145, D1120, D1351, D1208, space maintainers, D2930, primary-tooth pulpal therapy), adult-marker codes (D4341/D4342, D4355, D4910, dentures), D1110 (age 14 and up) and mixed. It also splits providers into pediatric, general and other by NPPES taxonomy.
2. Benchmark Virginia's code-level adult volume against DMAS published adult dental utilization. This measures how much HHS small-cell suppression (cells under 12 claims or beneficiaries) hides.
3. Add CMS monthly Medicaid enrollment for adults and children (data.medicaid.gov) as denominators. The 2023 adoptions overlap the start of unwinding.
4. Collect child fee-schedule changes around each adoption date. A child fee increase at the same time would confound the child outcome.
5. Verify every date in `policy_events.csv` against primary sources.

## Limitations

Category outcomes mix children and adults, so the child effect is not identified until the code-level panel is built. Geography comes from the provider's practice address. The adult-marker categories are heavily suppressed, so the +458% describes timing and should not be read as a magnitude. See [`docs/LIMITATIONS.md`](../../docs/LIMITATIONS.md) for the full data ledger.
