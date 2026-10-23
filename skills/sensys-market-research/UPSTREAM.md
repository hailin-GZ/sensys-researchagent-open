# Reuse and attribution

Immutable versions and hashes are in upstream-lock.json. Original upstream files and
license notices are retained under vendor; the host adaptation rules are in SKILL.md.

| Upstream | Included reuse | License | Adaptation |
|---|---|---|---|
| coreyhaines31/marketingskills | Customer Research and its two references; primary needs workflow | MIT | Consumer context, conditional output, evidence contract, primary research design only |
| anthropics/knowledge-work-plugins | User Research, Research Synthesis, Competitive Brief and connector explanations | Apache-2.0 | Real tool mapping, consumer alternatives, shared evidence and optional sections |
| ScrapeCreators/social-media-research-skills | Comment Mining and Product Demand Research methods | MIT | Actual public/supplied acquisition instead of assuming a paid API |
| Yui-cx/wechat-article-to-md-skill | HTMLToMarkdownParser class in scripts/wechat_converter.py | MIT | One translated comment; external adapter preserves raw bytes/attribution and verifies images; does not invoke upstream lossy formatter |

Yui-cx's original Chinese instructions and full source were reviewed and retained in
the build audit outside the distributable package. Only the needed converter class
and its license are distributed here. Its conversion algorithm is unchanged. Asset
download success is derived from saved bytes; failed references stay visible. Author
and account are separate nullable fields, and the uncleaned original response is saved.

Installed libraries are reused as dependencies rather than copied or reimplemented:
DDGS, requests, BeautifulSoup, markdownify, pypdf, python-docx and openpyxl. Exact direct
versions are in requirements.txt; the tested full environment is in dependency-lock.txt.

Other reviewed candidates were not made default dependencies: Firecrawl requires a
configured service for its hosted path; Crawl4AI adds browser setup unnecessary for
the currently verified public-page path; baoyu requires Bun/Chrome; Docling is useful
for complex OCR but unnecessary for text PDFs; last30days is a recent-signal specialist;
idea-reality-mcp is for software similarity, not generic consumer demand. They remain
valid conditional options after actual configuration and verification.

The external [hardtech-venture-judgment](https://github.com/2911642560-cmyk/hardtech-venture-judgment)
is a methodological reference, not bundled code. Its evidence distinctions, counterexamples,
stage/constraint focus and low-cost validation are relevant. Manufacturing and technical
review are conditional; its full framework is not imposed on all consumer research.
No copied friend code or instructions are distributed without an established license.

Search added other candidates including phuryn/pm-skills and consulting-oriented
research frameworks. The existing selected workflows already cover the necessary
research modes; fixed competitor/persona counts and comprehensive financial/marketing
reports were not added to every task. Selection favors relevant methods and executable
dependencies, not the number of imported skills.
