"""Recurrence model: after an animal leaves care (adopted or returned to owner), does it come back
within 180 days?

The casework version of this question is "will this family return to service?". The method is the same:
- one row per closed stay, label = a new intake within the window after the outcome
- censoring: only stays whose full 180-day window ends before the data cut can be labelled
- time-based split: train on earlier fiscal years, test on a later one (never a random split)
- report discrimination (AUC), calibration (Brier score, binned observed vs predicted) and lift,
  always against the base rate, so a model has to beat "predict the average" to count
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from shelter.db import connect

WINDOW_DAYS = 180
EXITS = ("Adoption", "Return to Owner", "Rto-Adopt")
CATEGORICAL = ["animal_type", "intake_type", "intake_condition", "outcome_type", "region_type"]
NUMERIC = ["log_days_in_care", "prior_intakes", "outcome_month"]
TRAIN_FYS = (2014, 2015)  # FY 2014-15 and 2015-16
TEST_FY = 2016            # FY 2016-17


def build_rows(con):
    (cut,) = con.execute("select max(intake_dt) from fct_stays").fetchone()
    rows = con.execute(f"""
        select s.stay_id, s.animal_type, s.intake_type, s.intake_condition, s.outcome_type, s.region_type,
               ln(1 + s.days_in_care) as log_days_in_care, s.intake_seq - 1 as prior_intakes,
               month(s.outcome_dt) as outcome_month, s.outcome_dt,
               case when month(s.outcome_dt) >= 4 then year(s.outcome_dt) else year(s.outcome_dt) - 1 end as fy,
               exists (select 1 from fct_stays n where n.animal_id = s.animal_id and n.intake_dt > s.outcome_dt
                       and n.intake_dt <= s.outcome_dt + interval {WINDOW_DAYS} day) as returned
        from fct_stays s
        where s.outcome_type in {EXITS}
          and s.outcome_dt + interval {WINDOW_DAYS} day <= ?
        order by s.stay_id  -- fixed row order, so the fit and the ranking are reproducible run to run
    """, [cut]).fetchall()
    cols = ["stay_id", *CATEGORICAL, *NUMERIC, "outcome_dt", "fy", "returned"]
    data = {c: np.array([r[i] for r in rows], dtype=object) for i, c in enumerate(cols)}
    return data, cut


def _X(data, mask):
    import pandas as pd  # sklearn's ColumnTransformer works best with a DataFrame
    return pd.DataFrame({c: data[c][mask] for c in CATEGORICAL + NUMERIC}).astype(
        {**{c: str for c in CATEGORICAL}, **{c: float for c in NUMERIC}})


def calibration_bins(y, p, n=5):
    order = np.argsort(p, kind="stable")
    out = []
    for chunk in np.array_split(order, n):
        out.append((float(p[chunk].mean()), float(y[chunk].mean()), len(chunk)))
    return out


def fit_and_score(con):
    data, cut = build_rows(con)
    train = np.isin(data["fy"], TRAIN_FYS)
    test = data["fy"] == TEST_FY
    y_tr = data["returned"][train].astype(int)
    y_te = data["returned"][test].astype(int)
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])
    models = {
        "logistic regression": Pipeline([("pre", pre), ("m", LogisticRegression(max_iter=2000, C=1.0))]),
        "gradient boosting": Pipeline([("pre", pre), ("m", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, random_state=0))]),
    }
    base = float(y_tr.mean())
    results = {"base rate (train)": {"auc": 0.5, "brier": float(brier_score_loss(y_te, np.full(len(y_te), base))),
                                     "p": np.full(len(y_te), base)}}
    for name, m in models.items():
        m.fit(_X(data, train), y_tr)
        p = m.predict_proba(_X(data, test))[:, 1]
        results[name] = {"auc": float(roc_auc_score(y_te, p)), "brier": float(brier_score_loss(y_te, p)), "p": p}
    k = max(1, len(y_te) // 10)
    for name, r in results.items():
        if name == "base rate (train)":
            # A constant prediction cannot rank, so its "top 10%" is any 10%: in expectation, the test rate.
            r["top_decile_rate"] = float(y_te.mean())
            continue
        top = np.argsort(-r["p"], kind="stable")[:k]
        r["top_decile_rate"] = float(y_te[top].mean())
    meta = {"cut": cut, "n_train": int(train.sum()), "n_test": int(test.sum()), "train_rate": base,
            "test_rate": float(y_te.mean()),
            "train_last_outcome": max(data["outcome_dt"][train]), "test_first_outcome": min(data["outcome_dt"][test])}
    return results, meta, y_te


def report(results, meta, y_te) -> str:
    lines = [
        "# Recurrence model: return within 180 days of leaving care", "",
        f"Rows: closed stays ending in adoption or return to owner, with the full {WINDOW_DAYS}-day window before the "
        f"data cut ({meta['cut']:%Y-%m-%d}). Train on FY 2014-15 and 2015-16 ({meta['n_train']:,} stays, "
        f"{meta['train_rate']:.1%} returned); test on FY 2016-17 ({meta['n_test']:,} stays, {meta['test_rate']:.1%} returned).", "",
        "| Model | AUC | Brier score | Return rate in top 10% |", "|---|---:|---:|---:|",
    ]
    for name, r in results.items():
        lines.append(f"| {name} | {r['auc']:.3f} | {r['brier']:.4f} | {r['top_decile_rate']:.1%} |")
    best = max((n for n in results if n != "base rate (train)"), key=lambda n: results[n]["auc"])
    lines += ["", f"Calibration of {best} on the test year (5 equal-size bins):", "",
              "| Mean predicted | Observed | Stays |", "|---:|---:|---:|"]
    for pred, obs, n in calibration_bins(y_te, results[best]["p"]):
        lines.append(f"| {pred:.1%} | {obs:.1%} | {n:,} |")
    lines += ["", "Lower Brier is better; the base rate row is the bar to beat. "
              "AUC says how well the model ranks; calibration says whether a predicted 20% really means 20%.",
              "Features: animal type, intake type and condition, outcome type, region type, log days in care, "
              "prior intakes, outcome month. No feature uses information from after the outcome date."]
    return "\n".join(lines) + "\n"


def main():
    results, meta, y_te = fit_and_score(connect())
    text = report(results, meta, y_te)
    out = Path(__file__).resolve().parent / "docs" / "results.md"
    out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
