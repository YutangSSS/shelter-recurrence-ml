from datetime import timedelta

import pytest

from shelter.db import DATA_DIR, connect


@pytest.fixture(scope="module")
def con():
    if not (DATA_DIR / "aac_intakes.csv").exists():
        pytest.skip("public data not downloaded: run `uv run python scripts/fetch_data.py`")
    return connect()


def test_models_match_the_harness_fingerprint(con):
    """fct_stays is identical to metric-report-harness's (MD5 over every row and column, captured 2026-11-13)."""
    got = con.execute("""
        select count(*), md5(string_agg(concat_ws('|', stay_id, animal_id, intake_seq, is_repeat_intake, intake_dt,
               intake_type, intake_condition, animal_type, region_type, custody_group, outcome_id, outcome_dt,
               outcome_type, outcome_subtype, deceased, days_in_care), chr(10) order by stay_id))
        from fct_stays""").fetchone()
    assert got == (80160, "d11c6b0d4adcce4aa79c0bcdeadddbac")


def test_split_censoring_and_bar(con):
    from recurrence import WINDOW_DAYS, build_rows, fit_and_score

    data, cut = build_rows(con)
    assert all(d + timedelta(days=WINDOW_DAYS) <= cut for d in data["outcome_dt"])  # every label fully observed
    results, meta, _ = fit_and_score(con)
    assert meta["train_last_outcome"] < meta["test_first_outcome"]  # time split, no overlap
    base = results["base rate (train)"]["brier"]
    for name in ("logistic regression", "gradient boosting"):
        assert results[name]["auc"] > 0.6
        assert results[name]["brier"] < base  # must beat predicting the average
