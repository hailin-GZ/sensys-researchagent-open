# Decision-relevant evidence coverage

Select applicable evidence roles before collecting many URLs:

| Role | Questions it can answer | Limitation |
|---|---|---|
| official_product | Features, price, policies and actual alternatives | Vendor statements do not prove efficacy/demand |
| user_voices | Experiences, workarounds, objections and purchase/abandonment | Selection bias; a thread is not a representative survey |
| crowdfunding | Rewards, pledges, updates, delays and delivery | Pledges do not prove sustained demand, delivery or efficacy |
| statistics_surveys | Population/context with definitions and sample design | Geography, year and denominator may differ |
| independent_reports | Industry/consumer evidence | Inspect methodology, funding and original data |
| scientific_research | Mechanism, measurement validity and study outcomes | Study design/population constrain causal claims |
| patents | Prior-art direction, published claims and application history | Not product proof, current validity or legal clearance |
| supplied_research | Authorized interviews, diaries, surveys and field notes | Separate actual observations from test fixtures |

URLs, mirrors or suppliers sharing an upstream do not create independent evidence.
Group original origins, query alternatives/negative reviews, inspect failed products
when relevant, and distinguish search leads from captured body evidence.

## Task-owned plan

Write a UTF-8 JSON file, then `capabilities.py plan --task TASK --file PLAN.json`:

```json
{
  "schema_version": "2.0",
  "decision": "Choose a problem and next experiment",
  "selected_capability_ids": ["tool:T002"],
  "excluded_modes": [{"mode": "sizing", "reason": "No denominator needed"}],
  "roles": [
    {"role": "official_product", "required": true, "reason": "Identify alternatives", "status": "missing", "source_ids": [], "gap": "Product pages not acquired"},
    {"role": "user_voices", "required": true, "reason": "Check observed problems", "status": "missing", "source_ids": [], "gap": "Need original experiences"},
    {"role": "patents", "required": false, "reason": "No technical novelty claim", "status": "not_relevant", "source_ids": [], "gap": ""}
  ]
}
```

Update actual IDs/statuses as work proceeds. Allowed statuses: captured, partial,
blocked, missing, not_relevant. Every role needs a reason; partial/blocked/missing
need a gap. Required roles cannot be not_relevant. Captured roles need usable source
records; search excerpts alone and failed pages cannot establish full coverage.
The host still reviews scope, pagination, relevance and independence. Counts alone
are not a coverage test.

Validation checks source references and blocks complete status when a required role
is incomplete. V1 tasks without a plan remain readable. Add a plan to upgrade a task;
never rewrite its historical acquisitions.

Research can finish partial with useful findings. Explain what was acquired, attempted,
unavailable and decision-limiting. Include contradictions and unknown willingness to
pay. A complete desk-research task is not market validation. Search cannot substitute
for actual interviews, purchases, engineering validation or clinical studies.
