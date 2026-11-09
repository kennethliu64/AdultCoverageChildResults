"""Build code-level panels for the adult-benefit / children's care analysis.

Reads the merged + geocoded claims file (gitignored, ~23M rows) and writes

  output/code_panel_state.csv      state x month x age group x provider type
                                    (small; safe to commit)
  output/code_panel_provider.parquet  NPI x month x age group, all states
                                    (local; do not commit). Treated and control
                                    states are chosen later, by design.py.

    python analysis/adult_dental_spillover/build_code_panel.py \
        --merged data/MergedHHS-NPI/merged_hhs_nppes_geo.csv

Age groups come from CDT codes whose descriptors or clinical use tie them to
one age band. Everything else is "mixed". The lists are a starting point;
check each code's share against a source with patient age before publishing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

OUT = Path(__file__).resolve().parent / "output"

# Primary-dentition or pediatric-descriptor codes.
CHILD = [
    "D0145",  # oral evaluation, patient under 3
    "D1120",  # prophylaxis, child
    "D1351",  # sealant, per tooth
    "D1208",  # topical fluoride, excluding varnish
    "D1510", "D1516", "D1517", "D1526", "D1527",  # space maintainers
    "D2930",  # prefabricated stainless steel crown, primary tooth
    "D3220",  # therapeutic pulpotomy (overwhelmingly primary teeth)
    "D3230", "D3240",  # pulpal therapy, primary teeth
]  # fmt: skip

# Codes almost never billed for children.
ADULT = [
    "D4341", "D4342",  # scaling and root planing
    "D4355",  # full-mouth debridement
    "D4910",  # periodontal maintenance
    "D5110", "D5120", "D5130", "D5140",  # complete dentures
    "D5211", "D5212", "D5213", "D5214",  # partial dentures
    "D5225", "D5226",  # flexible partials
    "D5410", "D5411", "D5421", "D5422",  # denture adjustments
    "D5730", "D5731", "D5750", "D5751", "D5760", "D5761",  # relines
]  # fmt: skip

# D1110 is "prophylaxis, adult" but is billed from about age 14. Kept separate.
TEEN_ADULT = ["D1110"]

PEDIATRIC_DENTIST = "1223P0221X"
GENERAL_DENTIST = "1223G0001X"

STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY",
}  # fmt: skip



def sql_list(xs: list[str]) -> str:
    return ", ".join(f"'{x}'" for x in xs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", type=Path, default=Path("data/MergedHHS-NPI/merged_hhs_nppes_geo.csv"))
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    con = duckdb.connect()
    con.execute(
        "CREATE TEMP TABLE fips(sf VARCHAR, st VARCHAR); INSERT INTO fips VALUES "
        + ", ".join(f"('{k}', '{v}')" for k, v in STATE_FIPS.items())
    )
    con.execute(
        f"""
        CREATE TEMP TABLE base AS
        SELECT
            f.st                                                   AS state,
            substr(regexp_replace(CAST(r.year_month AS VARCHAR), '[^0-9]', '', 'g'), 1, 4) || '-' ||
            substr(regexp_replace(CAST(r.year_month AS VARCHAR), '[^0-9]', '', 'g'), 5, 2) AS ym,
            CAST(r.servicing_npi AS VARCHAR)                       AS npi,
            CASE
                WHEN r.hcpcs_code IN ({sql_list(CHILD)})      THEN 'child'
                WHEN r.hcpcs_code IN ({sql_list(ADULT)})      THEN 'adult'
                WHEN r.hcpcs_code IN ({sql_list(TEEN_ADULT)}) THEN 'teen_adult'
                ELSE 'mixed'
            END                                                    AS age_group,
            CASE r.primary_taxonomy_code
                WHEN '{PEDIATRIC_DENTIST}' THEN 'pediatric'
                WHEN '{GENERAL_DENTIST}'   THEN 'general'
                ELSE 'other'
            END                                                    AS prov_type,
            r.claims_count                                         AS claims,
            r.beneficiaries_served_count                           AS benes,
            r.total_amount_paid                                    AS paid
        FROM read_csv('{args.merged.as_posix()}', header = true,
                      types = {{'county_fips': 'VARCHAR', 'servicing_npi': 'VARCHAR',
                               'primary_taxonomy_code': 'VARCHAR', 'total_amount_paid': 'DOUBLE'}}) r
        JOIN fips f ON LEFT(NULLIF(r.county_fips, ''), 2) = f.sf
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT state, ym, age_group, prov_type,
                   SUM(claims) AS claims, SUM(benes) AS benes, ROUND(SUM(paid), 2) AS paid,
                   COUNT(DISTINCT npi) AS n_npi, COUNT(*) AS n_cells
            FROM base GROUP BY ALL ORDER BY ALL
        ) TO '{(OUT / "code_panel_state.csv").as_posix()}' (HEADER)
        """
    )
    con.execute(
        f"""
        COPY (
            SELECT state, npi, prov_type, ym, age_group,
                   SUM(claims) AS claims, SUM(benes) AS benes, SUM(paid) AS paid
            FROM base
            GROUP BY ALL ORDER BY ALL
        ) TO '{(OUT / "code_panel_provider.parquet").as_posix()}' (FORMAT PARQUET)
        """
    )
    print(con.execute("SELECT age_group, SUM(claims) FROM base GROUP BY 1 ORDER BY 2 DESC").fetchall())


if __name__ == "__main__":
    main()
