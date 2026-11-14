-- One row per intake ("stay"), with the outcome that closed it, if any.
-- Rule: the closing outcome is the first outcome for the same animal at or after the intake
-- and before that animal's next intake. A stay with no such outcome but a later intake must have ended by
-- that next intake: it is closed there with outcome 'Not recorded'. Otherwise it is open at the data cut.
create or replace table fct_stays as
with ordered as (
    select
        i.*,
        row_number() over (partition by animal_id order by intake_dt, intake_id)  as intake_seq,
        lead(intake_dt) over (partition by animal_id order by intake_dt, intake_id) as next_intake_dt
    from stg_intakes i
),
candidates as (
    select
        s.intake_id,
        o.outcome_id,
        row_number() over (partition by s.intake_id order by o.outcome_dt, o.outcome_id) as rn
    from ordered s
    join stg_outcomes o
      on o.animal_id = s.animal_id
     and o.outcome_dt >= s.intake_dt
     and (s.next_intake_dt is null or o.outcome_dt < s.next_intake_dt)
)
select
    s.intake_id                                   as stay_id,
    s.animal_id,
    s.intake_seq,
    s.intake_seq > 1                              as is_repeat_intake,
    s.intake_dt,
    s.intake_type,
    s.intake_condition,
    s.animal_type,
    s.region_type,
    s.custody_group,
    o.outcome_id,
    coalesce(o.outcome_dt, s.next_intake_dt)      as outcome_dt,
    case when o.outcome_id is null and s.next_intake_dt is not null then 'Not recorded'
         else o.outcome_type end                  as outcome_type,
    o.outcome_subtype,
    coalesce(o.deceased, false)                   as deceased,
    date_diff('day', s.intake_dt, coalesce(o.outcome_dt, s.next_intake_dt)) as days_in_care
from ordered s
left join candidates c on c.intake_id = s.intake_id and c.rn = 1
left join stg_outcomes o on o.outcome_id = c.outcome_id;
