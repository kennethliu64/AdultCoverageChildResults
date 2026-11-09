# Human work before publication

Ordered by how much each item could change the result. Tick boxes as you go.

## Must do (could change or sink the finding)

- [ ] **Verify every policy date.** Replace each secondary source in `policy_events.csv` with the state plan amendment (medicaid.gov SPA search) or the state agency notice. Only HI and OK are primary-sourced so far. Then rerun `prelim.py`; the rules re-pick states automatically.
- [ ] **Check for missed policy changes.** Search 2016–2024 for adult dental changes in every control state, starting with SC and UT (flagged by the falsification check). Add anything found to `policy_events.csv`.
- [ ] **Resolve New Hampshire.** Adult claims rise before its April 2023 date and children's procedures fall 16%. Confirm the start date, any earlier pilot, and whether NH changed dental vendors or claims reporting at launch.
- [ ] **Confirm claims reporting did not change at adoption.** For each treated state, confirm adult and child dental claims run through the same vendor and encounter-reporting pipeline before and after. A vendor or managed-care change at the same time would create a fake effect.
- [ ] **Measure suppression.** Compare Virginia's adult dental volume in this data with DMAS's published adult dental utilization. Decide how to report suppressed volume (lower bound, or bounds).
- [ ] **Lock the analysis plan before more analysis.** Name one primary outcome (suggest: children's procedure codes, % of own baseline) and one primary specification. Register it (for example on OSF), stating honestly which results have already been seen.

## Should do (reviewers will ask)

- [ ] **Clinical review of the code lists** (Dr. Burton is ideal). Are D1208 and D1351 child-only in practice? Is the adult list right?
- [ ] **Children's fee changes.** Collect child fee-schedule changes around each adoption date; a concurrent child fee increase would confound the child outcome.
- [ ] **Enrollment denominators.** Add CMS monthly Medicaid/CHIP enrollment by adult and child (data.medicaid.gov) as a robustness check, because the 2023 adoptions overlap unwinding.
- [ ] **Specify the provider-level test** (general vs pediatric dentists, heterogeneity by county dentist supply) before running it.
- [ ] **Statistician review** of permutation inference with six treated states and of multiple-outcome correction.
- [ ] **Sensitivity to fixed choices.** Report results with other windows (for example 12/12, 36/18) and break thresholds (1.3×, 2×).

## Before submission

- [ ] **Literature search** in EconLit, SSRN and NBER, plus recent T-MSIS/TAF papers, to confirm nobody has published the provider-level version.
- [ ] **Pick a target journal** and frame for it (Health Affairs or JAMA Health Forum: policy; JHE or AJHE: economics).
- [ ] **IRB determination letter** (likely not human subjects research; journals will ask).
- [ ] **Pin the data version.** Record which HHS release (February or March 2026) and which NPPES snapshots were used.
- [ ] **Independent rerun.** A coauthor reruns everything from a fresh clone and gets identical numbers.
- [ ] **Authorship and sequencing.** Agree on authors (Eleni, Dr. Burton, CHOMP team) and whether the CHOMP data paper goes out first.
- [ ] **Repository visibility.** This fork is public. Decide whether preliminary results should move to a private repo until publication.
