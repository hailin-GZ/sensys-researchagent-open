# Standard and deep research

Depth controls effort within a decision, while the nine research modes select
methods. Do not load every method or platform because the user selected deep.
Map ordinary/normal research to `standard`, and explicit deep research to `deep`.
If no tier is given, use standard and state that choice. The user can request
"Use standard research for this idea" or "Continue this task with deep research."
Keep the selected tier in the brief, result, budget ledger and specialist handoff.

## Shared contract

Both tiers require decision-relevant breadth, retrievable original evidence,
counterevidence, provenance and the same integrity/semantic-support checks.
No tier is allowed to fabricate a quote, persona, survey, customer or market size.
Neither tier has a minimum source count: many duplicate URLs can be weaker than
a few relevant independent origins. Preserve useful older methods and archives.

For an early-stage product decision, assess three dimensions:

- **User needs:** observed situations, frequency/consequences, workarounds, unmet
  needs, objections and possible users. Public comments are a selected sample,
  not a representative prevalence estimate. User and purchaser may differ.
- **Commercial evidence:** substitutes, direct/adjacent competition, actual offers,
  hardware plus subscription/ongoing cost, and purchase signals. Grade each signal
  as problem discussion, stated intention, payment, or sustained use/retention.
  Self-reported purchases remain source opinions unless independently verified;
  reward pledges are commitments, not proof of delivery or retention. Competitor
  prices and survey responses support pricing hypotheses, not proven acceptance
  of our product. Identify the cheapest next price/demand experiment.
- **Product risks:** whether relevant features are feasible, what evidence supports
  vendor claims, actual delivery/reliability history, cloud dependence, permissions,
  privacy and important operating constraints. Distinguish an existing product's
  observed failures from a new concept's risks awaiting testing. Medical claims
  need appropriate authoritative evidence and validation; journals and environmental
  correlations do not establish a cause, diagnosis or therapeutic benefit.

For a narrow task such as summarizing supplied interviews or comparing two prices,
keep only relevant dimensions and explain exclusions. Do not force TAM, patents,
crowdfunding or fresh web queries into every result. A failed platform is not
absence of demand. A crowdfunding search with no match is not evidence that no
product exists: check names, regional variants, direct sales and substitutes.

## Differences in work

| Aspect | Standard | Deep |
|---|---|---|
| Decision | Identify plausible opportunity, objections and next test | Stress-test the decision and resolve high-impact uncertainties |
| Users | Main observed situations and plausible segments | Compare distinct segments, triggers, non-users and purchaser/user differences |
| Source roles | Cover relevant roles; expose decisive gaps | Follow gaps with more direct/independent evidence; reconcile conflicting origins |
| Commercial | Available offers and clearly graded demand/payment signals | Payment versus intention, total ownership cost, refunds/delivery and conditional price hypotheses |
| Product | Material feasibility, privacy and reliability risks | Failure histories, dependency/measurement limits and validation requirements |
| Follow-up | Initial pass plus one gap-directed pass if useful | Up to three gap-directed passes after the initial pass |
| Output | Concise findings, limits and cheapest next experiment | Segment/decision comparisons, contrary evidence and deeper validation plan |

The full deep workflow still applies to the same scoped decision. A price comparison
can explicitly exclude segments and engineering risks, while cross-checking terms,
regions, subscriptions and offer dates. Longer prose does not constitute deeper work.
Do not simulate real interviews; without actual participants/data, primary research
is a plan. An inability to resolve a decisive gap produces a partial result.

## Configurable local ceilings

The machine-readable defaults are [research-profiles.json](research-profiles.json).
These are starting ceilings, not statistical sample requirements or cost promises:

| Local operation | Standard | Deep |
|---|---:|---:|
| Fresh search attempts | 12 | 36 |
| Fresh capture/import attempts | 24 | 72 |
| Research rounds, including initial pass | 2 | 4 |
| Returned leads per query | 8 | 8 |
| Image attempts per source | 8 | 8 |

The synchronous helper rejects overlapping acquisition/management operations for
the same profile task. Run one task acquisition worker, and one heavy browser/OCR
worker across the 2-core / 8-GB host. The host must enforce the latter across tasks.
The helper does not benchmark RSS or automatically provision server resources.
Profile tasks reject local imports over 25 MB before reading their bytes, matching
the existing main-download ceiling. For a larger required report, use a suitable
remote/document tool with bounded output and retain original-file provenance;
mark the imported scope honestly. Do not interpret this limit as absence of data.

`constraints.research_limits` in a trusted brief can override these local ceilings;
unknown keys and invalid values are rejected. Limit search results to 50 and images
to 30 per source. Do not rewrite limits to evade a stop. Explicit host/user budget
changes need a recorded scope decision. Images beyond a cap remain in the registry;
if a decisive chart is omitted, use a targeted available visual tool and disclose
what was actually inspected. Never discard relevant evidence because it costs more.

Local `discover` and `capture` reserve one operation before work. Failures and forced
refreshes consume an attempt; intact fresh cache hits do not. Imports consume capture
attempts too. Counts are operations, not HTTP request totals: redirects and bounded
image fetches can issue additional requests. Cache age, request options and archive
integrity remain part of reuse; upgrade alone does not refresh unchanged material.
Search and image limits are capped before cache-key construction. Per-source caps
are identical across tiers so switching depth does not cause gratuitous reacquisition.

There is no model or paid API dispatcher in these helpers. The host must enforce
token, currency, elapsed-time and external MCP/API limits before those calls, using
real provider usage and bounded output. Do not report estimated token savings as
measured savings. A model's future report-writing allowance must be reserved before
research. Host tool attempts must be recorded in its own ledger; importing their
output alone does not account for the external work. Use free, direct/structured
access first, configured remote APIs next when useful, heavy browsers only for gaps.

## Run, continue and review

```sh
python scripts/research.py init --task TASK --brief brief.json --modes needs,competitors,voices --depth standard
python scripts/capabilities.py budget --task TASK
python scripts/capabilities.py round --task TASK --reason "Resolve the purchasing gap" --gap "No direct payment evidence for the target segment"
python scripts/capabilities.py depth --task TASK --select deep --reason "User requested deeper validation of payment and reliability"
python scripts/capabilities.py context --modes competitors,voices --depth deep
```

The initial pass is recorded at initialization. Before each additional pass, log
specific gaps and why more information may change the decision. Rank follow-ups
by decision impact and expected information gain; inspect existing blocks before
new searching. Tool cards should describe the actual executor, source role, access
and resource cost. Broaden only useful branches, not every tool or every platform.
Stop on adequate support, repetitive leads, budget ceiling, inaccessible decisive
material, or a question that requires fresh primary testing. Return findings already
supported, precise gaps and a cheapest next experiment. There is no source quota.

`depth --select deep` retains task/source/evidence IDs, original bytes, timestamps,
cache records and consumed counters. Brief overrides remain in force after switching.
It archives the previous depth review, invalidates finalization and marks the result
partial until the selected tier is reviewed. Old report/handoff files are historical
until regenerated; use result status and `finalized_at` to determine readiness.
Downgrading never resets counts. A legacy task can be assigned a tier explicitly;
known historic captures/search records are conservatively counted. Unrecorded external
work and historic research rounds cannot be reconstructed. Untouched old tasks keep
their original validation contract and have no new acquisition ceilings.

Write `result.depth_review` with the selected tier and `checks`. Each check needs
`check`, `status` (`assessed`, `gap`, `not_relevant`), `reason`, and a list of
`finding_refs` resolving to result findings. Standard completion requires
`decision_scope`, `source_roles`, `contrary_evidence`, `next_validation`. Deep also
requires `segments_and_situations`, `payment_evidence`, `product_risks`,
`independent_crosschecks`. For startup decisions, these extra deep checks are relevant;
for narrow tasks, justify exclusions. An assessment with no direct evidence must
explain its limits and cannot present a supported answer. A decisive gap uses `gap`
and partial status. A non-decisive unknown can be documented in an assessed check.

Complete profile tasks also require the existing source-role coverage plan, all
required roles captured, exact quotes, resolved finding references and declared host
semantic review. Mechanical review only verifies this contract, not entailment or
whether the host's exclusions are sound. An exhausted attempt budget does not by
itself invalidate a fully supported scoped answer, and never excuses missing evidence.

## Design references

- [GPT Researcher deep research](https://docs.gptr.dev/docs/gpt-researcher/gptr/deep_research)
  separates breadth, recursive follow-up and concurrency. We use bounded follow-up
  without adopting its parallel default or its cost/model estimates.
- [STORM](https://github.com/stanford-oval/storm) separates evidence collection from
  writing and uses multiple perspectives to guide questions. Here those perspectives
  are research prompts, not invented primary participants.
- [Customer Research](https://github.com/coreyhaines31/marketingskills/blob/main/skills/customer-research/SKILL.md)
  distinguishes existing materials, public signals and primary studies. This package
  retains its pinned bundled version and adapts it to consumer startup decisions.

These patterns inform the routing contract; the packages are not newly installed or
made mandatory dependencies. The existing pinned methods and licenses remain intact.
