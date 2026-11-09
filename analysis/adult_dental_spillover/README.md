# Adult Medicaid dental benefits and children's care: preliminary analysis

Research question: when a state adds adult Medicaid dental coverage, what happens to children's Medicaid dental care? Parents gaining coverage may bring children in more often (household spillover; Lipton 2021, JHE). Dentists who treat both age groups may also ration chair time toward newly covered adults (displacement). Buchmueller, Miller and Vujicic (AEJ: Policy 2016) found no crowding out of privately insured patients. Nobody has tested displacement of Medicaid children at the provider level.

This folder is a feasibility pass using only the category-level monthly state file CHOMP already ships. It cannot separate adult from child claims inside a category, so it answers three narrower questions. Is the first stage visible? How large is the adult inflow? Can a state-level design detect a plausible child effect?

## Reproduce

```bash
python analysis/adult_dental_spillover/prelim.py
```

Runs in about 15 seconds from a fresh clone (needs pandas, numpy, matplotlib). Writes to `output/`.

| File                              | Contents                                                                   |
| --------------------------------- | -------------------------------------------------------------------------- |
| `output/did_estimates.csv`        | DiD by outcome and state, permutation p-values, minimum detectable effects |
| `output/event_study_pooled.png`   | Pooled event study, four outcomes, with placebo bands                      |
| `output/event_study_by_state.png` | Event paths for each adopting state                                        |
| `output/state_screen.csv`         | Reporting-break and adult-share screen used to pick controls               |

## Design

Treated states and start months are VA 2021-07, ME 2022-07, MD 2023-01, TN 2023-01 and NH 2023-04. All five dates are provisional and need checking against each state plan amendment.

Controls are 19 states whose total claims have no reporting break and whose adult-marker share never jumps (AK, AL, AR, CT, GA, IA, KS, LA, MA, MS, NC, NJ, NM, NY, OR, RI, WA, WI, WY). The screen removed two kinds of states. Some have reporting breaks as large as any policy effect. Texas total claims rise about 20x between 2020 and 2021, Delaware reports almost nothing from 2019 through mid-2021, and FL, MN, MO, PA, IN and WV have similar problems. Others show adult-share jumps that look like their own policy changes (MI, KY, SC, UT, HI, AZ in 2023; OK and WV in 2021–22; CA, CO, IL, VT trending up). For orthodontics, controls are limited to the 12 states with real ortho volume, since KS and OR report none.

Each treated state gets a window of 24 months before and 18 months after its start date, using log(1 + monthly claims). March to June 2020 is dropped, and the panel ends 2024-09 to avoid the late-2024 claims lag (ledger L02). The estimate is a simple 2×2 DiD against the control mean. Inference is by permutation: every control is run as a placebo at each treated date. For the pooled estimate, 5,000 draws assign five distinct controls to the five dates. The MDE is 2.8 × the placebo SD (80% power, two-sided 5%).

## Results

| Outcome                                               | Pooled DiD | Permutation p | Pooled MDE |
| ----------------------------------------------------- | ---------: | ------------: | ---------: |
| Adult-marker claims (perio, prosthodontics, implants) |      +368% |       < 0.001 |       ±89% |
| All dental claims                                     |     +11.6% |       < 0.001 |      ±7.9% |
| Preventive + diagnostic claims                        |     +11.2% |       < 0.001 |      ±7.9% |
| Beneficiary-months                                    |     +10.6% |       < 0.001 |      ±7.7% |
| Orthodontic claims (child-only proxy)                 |     −13.2% |          0.29 |       ±42% |

By state, total claims rose 12% in VA, 14% in ME, 28% in MD and 10% in TN. NH moved −3% (p = 0.60). With a 12-month pre-window the pooled total is +9.7%. Dropping NH gives +15.7%.

The first stage is unmistakable. Adult-marker claims rise within the first three months of each benefit and stay up. Total claims ramp up over about six months. That ramp is consistent with adults entering the system and suggests no large immediate collapse in children's volume.

## What this means for the paper

1. The adult inflow is modest. If children's volume were unchanged, adults account for roughly 10–16% of pre-period claim volume in the first 18 months.
2. A state-level design cannot detect displacement. The pooled MDE on total claims is about 8%. Code-level child outcomes aggregated to the state will be at least that noisy. Displacement of 8% would mean children lost two-thirds of the adult inflow. Any plausible effect (a quarter of the inflow is about 3%) falls below detection with five treated states.
3. The child question therefore has to be answered within state at the provider level. Compare children's claims at general dentists (who absorb new adults) with children's claims at pediatric dentists (taxonomy 1223P0221X, who mostly do not) before and after adoption. Use heterogeneity by each dentist's pre-period Medicaid volume and by county dentist supply. Thousands of providers per state give the precision the state panel lacks, and the comparison is identified inside each state.
4. Orthodontics is a poor child proxy. Its MDE is ±42%, NH ortho drops sharply in 2021H2 well before adoption, and orthodontists rarely take adult Medicaid anyway. It works only as a check for reporting artifacts.
5. NH is suspect. Its adult-marker series rises from about 20 months before the April 2023 start date, and total claims do not move. Either the date is wrong, an earlier partial benefit existed, or NH adult claims flow through a channel this data misses. Resolve this before including NH.

## Next steps (need raw data, not in this repo)

Steps 1 and 2 are scripted. Anyone with the local merged file can run

```bash
python analysis/adult_dental_spillover/build_code_panel.py --merged data/MergedHHS-NPI/merged_hhs_nppes_geo.csv
```

It classifies every claim as child-marker, adult-marker, teen-and-adult (D1110) or mixed, and splits providers into pediatric dentists (1223P0221X), general dentists (1223G0001X) and other, using the taxonomy the merge already attached. It writes `output/code_panel_state.csv` (small, commit it) and `output/code_panel_provider.parquet` (NPI-level, keep local). The code lists sit at the top of the script.

1. Rebuild at code level from the merged file. Child markers include D0145, D1120, D1351, D1208, space maintainers, D2930 and primary-tooth pulpal therapy. Adult markers include D4341/D4342, D4355, D4910 and denture codes. D1110 is billed from about age 14, so it stays in its own group.
2. Separate pediatric from general dentists by NPPES primary taxonomy.
3. Benchmark Virginia's code-level adult volume against DMAS published adult dental utilization to measure how much HHS small-cell suppression (fewer than 12 claims or beneficiaries per cell) hides.
4. Add CMS monthly Medicaid enrollment split into adults and children (data.medicaid.gov) as denominators. The 2023 adoptions overlap the start of unwinding.
5. Collect child fee-schedule changes around each adoption date. A child fee increase at the same time would confound the child outcome.

## Limitations of this pass

Every outcome here mixes children and adults except adult markers and orthodontics, so the child effect is not identified. Geography comes from the provider's practice address. Treated dates and the control list are provisional. The adult-marker categories are heavily affected by small-cell suppression, so the +368% describes timing and should not be read as a magnitude. See [`docs/LIMITATIONS.md`](../../docs/LIMITATIONS.md) for the full data ledger.
