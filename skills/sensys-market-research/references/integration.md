# Invocation and result handoff

## Current host invocation

Ask the host to read this package's SKILL.md, then execute its relevant upstream
instructions and helper calls. A skill folder outside the host's registered skill
directories can be used by explicit path; automatic discovery depends on host setup.
Do not imply that downloading this package changes the running host's registry.

Create a task brief as a UTF-8 JSON file:

```json
{
  "question": "Which unmet needs should this consumer product address?",
  "decision_to_support": "Choose a segment and the next validation experiment",
  "research_depth": "standard",
  "research_scope": {
    "product_or_scene": "A wearable recording and contextual-memory assistant",
    "target_population": null,
    "geography": null,
    "time_range": "Current products and recent feedback"
  },
  "provided_materials": [],
  "constraints": {"time_budget": null, "cost_budget": 0},
  "requested_outputs": ["research report", "evidence package"],
  "language": "en"
}
```

Run from the skill directory with the prepared Python environment:

```sh
python scripts/research.py doctor
python scripts/research.py init --task /path/to/task --brief /path/to/brief.json --modes needs,competitors,voices,crowdfunding,validation
python scripts/research.py discover --task /path/to/task --query "wearable AI recorder user experiences" --limit 8
python scripts/research.py capture --task /path/to/task --url https://www.omi.me/ --category competitor --max-images 8
python scripts/research.py capture --task /path/to/task --file /path/to/interviews.txt --category supplied_research
```

For explicit deep research, set brief `research_depth` to `deep`, or pass `--depth
deep` with an absent/matching brief field. Conflicting choices fail before creating
a task. With neither supplied, initialization records `standard`. The nine modes
are independent of depth; changing depth does not enable every tool or method.
See [research-depth.md](research-depth.md) for ceilings, review and continuation.

```sh
python scripts/capabilities.py profiles
python scripts/capabilities.py budget --task /path/to/task
python scripts/capabilities.py depth --task /path/to/task --select deep --reason "User requested deep research"
python scripts/capabilities.py round --task /path/to/task --reason "Resolve decisive gaps" --gap "No independent delivery evidence"
python scripts/capabilities.py context --modes competitors,voices --depth deep
```

Trusted brief `constraints.research_limits` overrides only local operation ceilings:
`search_queries`, `captures`, `research_rounds`, `results_per_query`,
`images_per_source`. Smaller user ceilings remain in force on upgrade. The budget
ledger tracks attempts, managed rounds and selection history; it does not invent
token/cost measurements for calls performed by the host.

Read `sources.json` and the selected source's `blocks.json`. Register only an exact
quote you actually inspected:

```sh
python scripts/research.py evidence --task /path/to/task --source s0001 --block p0001 --quote "An exact excerpt from the stored block" --role vendor_claim
```

The host writes summary/findings/limitations into the initialized result.json. Assign
each finding a unique ID, kind and existing evidence_refs. Keep acquisition states,
study limits, contradictions and undecided questions. Set `support_reviewed` only
after reviewing every cited claim. Then:

```sh
python scripts/research.py validate --task /path/to/task
python scripts/research.py finalize --task /path/to/task
```

CLI commands return JSON. Invalid inputs and failed validation exit with code 2.
`capture` and `discover` can return a recorded acquisition failure with code 0 because
the operation successfully recorded that failure; inspect the returned status.
Network retries and images have bounded budgets. A task root belongs to one executing
agent at a time; the JSON store is not a concurrent database. Do not run simultaneous
mutating calls against the same task root. Different task roots can run independently.

## Version 2 discovery, coverage and cooperation

Keep the callable surface small. The additional helper offers deterministic metadata
discovery and evidence exchange; it does not install or call arbitrary catalogue entries.

```sh
python scripts/capabilities.py lookup --query "comment-mining" --kind skill --limit 4
python scripts/capabilities.py describe --id tool:capabilities
python scripts/capabilities.py context --modes competitors
python scripts/capabilities.py plan --task /path/to/task --file /path/to/coverage-plan.json
python scripts/capabilities.py retrieve --task /path/to/task --query "subscription" --limit 4 --max-chars 1200
python scripts/capabilities.py handoff --task /path/to/task
python scripts/capabilities.py cache-stats --task /path/to/task
python scripts/research.py capture --task /path/to/task --url https://example.com/ --max-age 86400
python scripts/research.py capture --task /path/to/task --url https://example.com/ --refresh
```

The coverage plan, cache log and handoff are additive task files; old v1 tasks without
them remain valid. Handoff IDs are scoped by `task_id`, and paths refer to the accompanying
task bundle. An available external connector can import its actual output through
`capture --file ... --source-url ... --method ... --scope excerpt`, or full scope only
when the complete original was genuinely obtained. See [compatibility.md](compatibility.md).

Coverage is reviewed by the host. A required role that is missing, blocked or only an
excerpt prevents a new plan from passing validation as complete. No plan is required
retroactively for old tasks. Cache reuse requires matching parameters, freshness and
intact archived material; refresh preserves the previous source record.

## Future backend contract

Offer two selector values: **Standard research** (`standard`, default) and **Deep
research** (`deep`). Send the selection as request/brief `research_depth`, display
the planned scope and effective budget, and validate the value server-side. Reuse
the existing task when continuing; call `research_depth.select` with a recorded
reason rather than creating a new task or resetting counters. The helper also offers
`research_depth.status` and `research_depth.next_round`. Regenerate report/handoff
after reviewing the selected tier. The host dispatcher must enforce its model-token,
cost, elapsed-time and external-tool budgets using real usage, including report
writing. Local acquisition ceilings do not cover calls made by other executors.

Workspace web previews are unchanged: they do not yet execute GPT research. This
upgrade supplies the usable Skill/CLI selection and the future UI/backend contract.

The backend receives a brief and available capabilities, loads SKILL.md and the selected
references, and exposes these functions: `init_task`, `discover`, `capture`,
`add_evidence`, `validate`, `finalize`. The model chooses queries, sources, modes,
interpretations and next steps. The executor calls the functions and returns their
actual JSON. Import `scripts/research.py` with its scripts directory on sys.path,
or call the CLI with an argument list; never concatenate user text into shell code.
It may additionally expose `lookup`, `describe`, `context_manifest`, `save_plan`,
`retrieve`, `handoff` and `cache_stats` from `scripts/capabilities.py`. Start with these
small interfaces and load only selected tool schemas/instructions. The catalogue is
not a function schema array and must not be sent wholesale in every model request.

Continue the model/tool loop until the selected scope is fulfilled or a real stopping
condition applies. The model writes the evidence-backed result, reviews support,
finalizes it, and returns the result/report paths. On follow-up, load the existing
brief/manifests and add evidence instead of rerunning every source. A selected mode
is routing metadata, not permission for external actions or paid services.

This is a tested execution contract for a future backend, not an implemented GPT API
service. Model keys, tool credentials, private instructions and acquisition logic stay
server-side. Tool availability in this desktop host does not transfer automatically.
Research artifacts remain task-local; the skill package contains no user recordings
or service credentials. Use relative artifact paths for migration.
