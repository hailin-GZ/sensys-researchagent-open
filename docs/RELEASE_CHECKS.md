# Public source release checks

This English distribution was prepared in an independent source directory. The deployed runtime source and bundled method library were compared against the local checkout before selection. UI differences were line endings only; newer local asynchronous transport regression tests were retained. No production database, credential store, or conversation archive was copied into the public tree.

## Local verification

- Agent regression: 160 tests, no failures, one platform-specific skip.
- Research method regression: 82 tests passed, including three fresh-checkout browser-path checks.
- Administrator regression: 11 tests passed.
- User access regression: 9 tests passed.
- Python and JavaScript syntax checks passed.
- All 247 bundled method paths and supporting-document integrity hashes were checked.
- English localization includes UI, administrative messages, model instructions, source-catalog labels, and project documentation. Multilingual matching fixtures remain synthetic or anonymized data represented with Unicode escapes.
- Production hostnames and identifiers were replaced with reserved example values. Real-conversation-derived company fixtures were replaced with an invented example company.
- Third-party documentation examples resembling credentials were removed; modified files carry notices and updated local hashes. No installed SDK, browser binary, provider configuration, or account cache is bundled.
- Browser discovery uses the standard Playwright installation cache on every platform, or an explicit executable override; no former workstation browser path is required.
- Full-tree secret scanning and local comparison against privately held credentials and encoded variants found no remaining matches.

Model routing, evidence contracts, publication checks, usage settlement, cancellation, and access isolation are tested offline using synthetic data and mocked provider responses. UI checks use a separate temporary database, generated test identities, and no model worker or provider profile. This publication process does not make a new claim of live compatibility with every model provider or source.

## Publication procedure

Only an audited source tree is committed. The complete indexed tree and all reachable historical Git blobs are scanned before upload. The uploaded commit is then downloaded again, compared byte-for-byte with the local commit, and scanned again. Publication receipts are kept outside the repository so they do not include private environment details.

No audit proves the absence of every possible unknown vulnerability or secret format. Re-run these checks on future contributions and before publishing release archives.
