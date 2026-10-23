# Executable tools and fallback paths

The portable helper is `scripts/research.py`; run `python scripts/research.py doctor`.
Install requirements in a task-owned virtual environment. It uses upstream DDGS for
key-free search, requests + BeautifulSoup for public capture, markdownify for general
HTML conversion, a licensed Yui-cx converter excerpt for WeChat, pypdf for PDF text,
python-docx for Word paragraphs/tables, and openpyxl for spreadsheet rows/formulas.
It is an adapter and evidence store, not a replacement crawler or autonomous model.

| Operation | Real default | Alternate path and state |
|---|---|---|
| Discover | `discover --query ...` / DDGS text search | Available host web search; retain query, result URLs, snippets and actual retrieval method |
| Public page | `capture --url ...` | Host browser or configured crawler for dynamic pages; import output with provenance |
| WeChat article | `capture --url https://mp.weixin.qq.com/s/...` | Public authorized article export; historical lists/subscription require a separately verified service |
| Images | Capture's original-byte image downloader + assets manifest | Authorized host downloader; failed or budget-omitted references remain visible |
| PDF / Word / table | `capture --file ...` | A real OCR/document tool for scans, legacy .doc/.xls or complex layout; retain original and locator mapping |
| Comments | Bounded Bilibili samples via `platform_probe.py`; public page or supplied JSON/CSV/text with provenance | Other social connectors/APIs require separate verification; see `access.md` |
| Crowdfunding | Public campaign/story/comments/update pages | Host browser or authorized exports; unavailable metrics/comments remain unknown |
| Evidence | `evidence`, `validate`, `finalize` | Model/human must verify semantic support and coverage |
| Capability selection | `capabilities.py lookup`, `describe`, `context` | Short metadata cards and selected instruction hashes; no automatic install/dispatch |
| Coverage and cooperation | `capabilities.py plan`, `retrieve`, `handoff` | Task-scoped role gaps, bounded exact locations and compatible structured export |
| Reuse | Fresh intact capture/discovery cache + `cache-stats` | `--refresh` for volatile/decisive facts; this is not provider prompt-cache telemetry |

The Agent host's `search_sources` additionally supports Responses native
`web_search` when `native_web_search` is enabled for a supplier verified with an
actual tool receipt. It archives queries, source URLs, response IDs and provenance.
Only URLs from real hosted source records/citation annotations become leads;
model-proposed uncited URLs are excluded. Hosted snippets are not original-body
evidence: continue with capture, reading and literal quotation registration.
Missing or failed hosted receipts remain failures, not model-memory search results.
Disabling this setting uses the portable DDGS discovery path. This does not imply
that every Responses-compatible supplier implements hosted search.

Raw HTTP does not execute JavaScript. `complete_body` means a chosen HTML container
was extracted; the host still verifies pagination, missing fields and body boundaries.
Default selection prefers WeChat content, a main container, or a sole article. Multiple
article cards without a main container are retained as partial material until a reviewed
selector is supplied. Both image tags and video poster images use the asset registry;
an omitted poster retains its original public URL.
Use `--selector` for a reviewed site container. A challenge/login page, empty selector,
or brief navigation shell is not a successful capture. Search results are leads,
not downloaded article bodies. Capture files are bounded and redirects are checked;
private network addresses and credential-bearing URLs are rejected.

The default HTTP adapter ignores ambient proxy and netrc credentials. This does not
prove bypass of system TUN routing. Configure a different host executor if deployment
network access requires it, preserving provenance. Do not alter global network settings
to make a source appear accessible. Search backend failures are recorded; try a bounded
different engine or the actual host search, then return limitations. No CAPTCHA bypass.

Some local TUN gateways resolve public hostnames to benchmark addresses in 198.18.0.0/15.
After confirming that behavior, set `SENSYS_ALLOW_BENCHMARK_DNS=1` for this executor
process only. This allows hostname-based requests through that gateway and records
the choice in each source; it still rejects literal non-public IPs and ordinary private
address ranges. Leave it unset on a deployment without such a gateway. No system
proxy/DNS settings are modified by this option.

For host-tool captures, save the actual tool output as supplied material and retain
the original source URL, retrieval time, acquisition method, excerpt/full-body scope
and any truncation in its source record. Do not call a cloud reader's result a local
HTTP download. Prefer original files to excerpts when obtainable.

## Agent 2.0.0 public capture adapter

The Agent host additionally registers `scrapling_capture(url, category, mode)` with
`http`, `dynamic`, and `stealth` modes. It uses pinned Scrapling 0.4.15, not an
uninstalled catalogue entry. Ordinary capture may attempt its HTTP adapter once
after a network/error/shell result; use dynamic or stealth only when rendered
public content is needed. Honor an explicit user request to use this tool when
appropriate. No credentials, authenticated sessions or automatic challenge solving.
The host consumes one capture before network work, retains failure states and
hashes, checks redirects/subrequests, and enforces byte/process deadlines.
Rendered DOM is an excerpt, not proof of a full original page. A failed attempt
never becomes a successful evidence body. Use actual open-access identifiers and
repositories when publishers remain blocked. Internal method/tool identifiers and
this routing description are not user deliverables; public source URLs and
research-subject evidence remain deliverable under the host disclosure boundary.
