-- One row per outcome event. Exact duplicates (same animal, same minute, same type) are removed first.
-- Rows with no outcome_type are kept and labelled, never dropped silently.
create or replace table stg_outcomes as
with deduped as (
    select * from raw_outcomes
    qualify row_number() over (partition by animal_id, datetime, outcome_type order by outcome_subtype nulls last) = 1
)
select
    row_number() over (order by animal_id, datetime, outcome_type) as outcome_id,
    animal_id,
    datetime                                      as outcome_dt,
    coalesce(outcome_type, 'Unknown')             as outcome_type,
    outcome_subtype,
    outcome_type in ('Died', 'Euthanasia')        as deceased
from deduped;
