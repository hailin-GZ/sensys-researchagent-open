# Evidence contract

Each task has brief.json, sources.json, evidence.json, result.json, report.md and
source bundles. Source bundles have source.json, raw.*, content.md, blocks.json,
and assets.json. Paths are relative to the task root and must remain inside it.
The raw bytes are immutable evidence; conversion output is a derived artifact.

Evidence fields: evidence_id, source_id, block_id, quote, context, evidence_role.
Quotes must be exact substrings of the captured block. PDF block IDs encode the PDF
page sequence; printed page numbers, if different, belong in the claim limitations.
Paragraph IDs locate extracted content, not the original site's DOM. Keep the URL
and original bytes for independent inspection.

Finding fields: finding_id, statement, kind, evidence_refs, limitations.
Allowed kinds: fact, source_opinion, inference, hypothesis, unknown. External facts,
source opinions and inferences require evidence. Hypotheses/unknowns without evidence
must explain the gap. Set support_reviewed=true only after a model or human reads
the referenced blocks and confirms that the statement is supported at its stated
scope. A literal quote check and source hash check do not perform that review.

The helper checks path existence, raw/Markdown/block/asset-registry/source-record hashes,
registry consistency, actual image decoding (or SVG structure), exact quotes,
resolved evidence IDs, finding kinds and declared semantic review. It reports asset
failures and sources with partial/no body. Findings may cite a partial source only
with an explicit acquisition/scope limitation. Failing required checks prevents
finalize. A genuine partial research result can still be finalized as partial.

Acquisition statuses: complete_body (selected container extracted; human coverage
review still required), partial_body (fallback/known missing content), snippet_only,
structured_data, supplied_text, login_required, captcha, not_found, network_error,
parse_error, shell_only. Raw HTML completeness is not proved by HTTP 200 or length.
Review body start/end, pagination, comments, collapsed sections and important tables.
Unavailable fields remain null. Record method, sample, population, dates, definitions,
units and currency for claims that depend on them.

Group independent origins with origin_id and duplicate_of. Automated content hash
deduplication catches exact duplicates only; identify reposts and shared studies
manually. Do not count copies, individual comments on one thread, promotional claims,
or model summaries as independent validation. Quote only what is necessary and
observe the source's reuse conditions; private materials stay within their authorized scope.

Task statuses: complete, partial, needs_input, failed. Completion refers to the
executed scope, not market validation. Any decisive unanswered question or incomplete
core evidence requires partial/needs_input. List conflicts, failed_sources,
missing_evidence, assumptions, and next_steps. No generic success probability.
