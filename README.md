# shelter-recurrence-ml

After an animal leaves a shelter (adopted or returned to its owner), will it come back within 180 days?
This is the same question as "will this family return to services?" in casework, asked on public data.
The method is the point: honest labels, a time-based split, and results always shown against the base rate.

## Result (test year FY 2016-17, 11,524 stays, 11.3% returned)

| Model | AUC | Brier score | Return rate in top 10% |
|---|---:|---:|---:|
| Base rate (predict the training average) | 0.500 | 0.1001 | 11.3% |
| Logistic regression | 0.653 | 0.0975 | 22.2% |
| Gradient boosting | 0.662 | 0.0967 | 21.6% |

This is a modest model, and the README says so. It ranks well enough that the 10% it flags return at about twice the
base rate, and its predictions are calibrated: in each fifth of the test year, the predicted and observed
return rates are within 2.3 points. The full output is in [`docs/results.md`](docs/results.md).

## Method

- **One row per closed stay** ending in adoption or return to owner. The label is a new intake of the same
  animal within 180 days after the outcome.
- **Censoring.** A stay is labelled only if its full 180-day window ends before the data cut. Otherwise a
  recent adoption would be counted as "did not return" just because there hasn't been time.
- **Time split, never random.** Train on FY 2014-15 and 2015-16 (21,514 stays, 10.2% returned), test on
  FY 2016-17. Every training outcome happens before every test outcome.
- **No leakage.** Every feature is known on the outcome date: animal type, intake type and condition, outcome type,
  region type, log days in care, number of prior intakes and the outcome month.
- **Against the base rate.** The Brier score is compared with predicting the training average. The test
  requires both models to beat it, and to reach an AUC above 0.6.
- **Reproducible.** Rows load in a fixed order and ties sort stably, so reruns give identical output. CI
  reruns the model and fails if `docs/results.md` changes.

## Run it

```bash
uv run python scripts/fetch_data.py      # public data, pinned revision, SHA-256 checked
uv run pytest -q                         # 2 tests: fingerprint, and split + censoring + beats the base rate
uv run python recurrence.py              # fits both models, rewrites docs/results.md
```

`models/*.sql` builds the table of stays in DuckDB. It is the same table as in
[metric-report-harness](https://github.com/YutangSSS/metric-report-harness): the tests check an MD5 over
every row and column (80,160 rows).

## Data

Austin Animal Center intakes and outcomes (80,187 intakes, Oct 2013 to Mar 2018), City of Austin open data, mirrored on Hugging Face as
[jason1966/aaronschlegel_austin-animal-center-shelter-intakes-and-outcomes](https://huggingface.co/datasets/jason1966/aaronschlegel_austin-animal-center-shelter-intakes-and-outcomes).
