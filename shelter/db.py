"""Build the DuckDB database: raw CSVs -> staging tables -> fct_stays."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"


def connect(
    intakes_csv: Path | str = DATA_DIR / "aac_intakes.csv",
    outcomes_csv: Path | str = DATA_DIR / "aac_outcomes.csv",
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        "create table raw_intakes as select animal_id, datetime::timestamp as datetime, intake_type, "
        "intake_condition, animal_type, found_location from read_csv_auto(?, header=true)",
        [str(intakes_csv)],
    )
    con.execute(
        "create table raw_outcomes as select animal_id, datetime::timestamp as datetime, outcome_type, "
        "outcome_subtype from read_csv_auto(?, header=true)",
        [str(outcomes_csv)],
    )
    build_models(con)
    return con


def build_models(con: duckdb.DuckDBPyConnection) -> None:
    for sql_file in sorted(MODELS_DIR.glob("*.sql")):
        con.execute(sql_file.read_text())
