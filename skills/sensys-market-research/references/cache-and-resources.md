# Reuse, context budget and the 2-core / 8-GB profile

Distinguish task artifact/query reuse (implemented here), bounded evidence retrieval
(implemented here), and model-provider prompt caching (depends on host/provider).
A stable instruction prefix can help the latter; this package does not enable it
or claim measured provider hits or token savings.

## Acquisition reuse

Capture defaults to max age 86,400 seconds; discovery to 3,600 seconds. These are
configurable starting values, not universal freshness guarantees. Prices, current
availability, policy and rapidly changing topics may need fresh acquisition.
`--refresh` or `--max-age 0` bypasses reuse.

```sh
python scripts/research.py capture --task TASK --url https://example.org/ --max-age 3600 --max-images 4
python scripts/research.py discover --task TASK --query "recent product failures" --refresh --limit 6
python scripts/capabilities.py cache-stats --task TASK
python scripts/capabilities.py retrieve --task TASK --query "humidity privacy" --limit 6 --max-chars 1800
```

Capture keys include target, selector, image budget, scope, method, origin override,
local-file digest and parser version. Stored hashes, source records and saved assets
are verified before a hit. Expired, changed, corrupt or failed archives are not reused
as success. V1 records without keys are reacquired when requested; originals remain.
Preserve the original retrieval time, partial status and failed assets on reuse.

Caches are task-local and single-writer, with no cross-user material sharing.
Failure records remain; the host chooses bounded alternatives. New acquisitions
remain distinct and exact-content duplicates retain their original origin grouping.

Retrieved blocks keep IDs, URL, dates and acquisition status; truncation is explicit.
Large blocks return a window around the first matching term with `char_start` and
`char_end` offsets into the original block. Retrieve a more specific term or inspect
the archived block when a bounded window does not contain sufficient context.
Read the original block when missing context matters, and register exact quotations
through the existing evidence helper. Send relevant evidence, brief and current-stage
methods rather than catalogs, raw HTML, binary assets or full repeated transcripts.

Keep core instruction ordering stable; dynamic user input/evidence follows it.
Context manifests identify versioned content, not a provider-cache hit. Do not rewrite
timestamps/headers needlessly or imply application reuse is API prompt caching.

## Resource-aware execution

Research effort is selected independently through standard/deep profiles in
[research-depth.md](research-depth.md). New profile tasks enforce fresh search and
capture/import ceilings, cap returned leads/images, and reject overlapping local
acquisition/management operations for the same task. A deeper profile grants more
targeted sequential work, not more concurrent workers. Upgrades retain archive IDs,
retrieval times and consumed counts; only changed, stale or corrupt material needs
reacquisition. Model tokens, external tools, host-wide concurrency, money and elapsed
time remain the host dispatcher's responsibility.

Prefer lightweight HTTP, SDK/CLI or remote routes when adequate. Budget request count,
bytes, time, images and paid calls; use bounded batches/pages/comments and incremental
acquisition. Do not install the catalog or a local language model.

For two cores, begin with serial acquisition and one mutating operation per task root.
Small HTTP concurrency across separate tasks may be added after measurement. Start
browser/OCR/model-heavy work only when needed, initially one active worker. Reserve
RAM for the OS and backend; 8 GB is not a tested peak guarantee. Measure deployment
memory/disk and then set limits. Windows samples do not certify Linux capacity.
