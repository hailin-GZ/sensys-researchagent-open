# Source access and verified scope

The source catalog contains the user's 95 requested work items, not 95 successful
connectors or distinct domains. The 2026-10-02 snapshot is an observation, not a
service guarantee. Select sources needed for the research question; do not probe
all 95 during every research task.

Use `research.py capture` for a known public URL. When the optional transport is
installed, `platform_probe.py --platform web --url URL --task TASK` uses curl_cffi
with bounded downloads and the same original/Markdown/source manifests. This is
an alternative HTTP transport, not permission to bypass challenges or paywalls.
Install the optional dependency from `requirements-platform.txt` in a local venv.

For public Bilibili video discussion samples:

```powershell
python scripts/platform_probe.py --platform bilibili --query "AI voice recorder" --limit 3 --task PATH
```

The helper retains search/reply JSON and exports `platform-sample.json` with
comment IDs, parent IDs, timestamps, exact text, source IDs and JSON pointers.
HTTP 200 with a nonzero application code is rejected. A first page, empty result
or embedded child replies do not establish complete comment coverage. The host
still assesses topical relevance, spam, sampling and the support of findings.

For YouTube discovery, the reviewed yt-dlp path works without a personal browser
profile in this executor. Search metadata succeeded; the attempted video/comment
extraction required bot-verification login. Do not promote it to verified comment
access. The optional dependency is intentionally not invoked for every task.

For WeChat, a concrete article URL and matching account identity are required.
Four accounts yielded original article samples in this run, including old
2021 and 2019 samples. Other publishers' website articles, reposts, author profiles and
search summaries are separate channels. Migrated account pages are not articles.

Crowdfunding campaign pages can work when their platform homepages do not.
Verify campaign description, pledges, rewards, comments and updates separately.
A displayed comment count or empty comment shell is not comment text. Country,
currency, campaign date and reward/donation/investment/membership models matter.

An anonymous browser obtained one visible Facebook comment; this requires a
browser executor and is not implemented by the HTTP helper. Instagram yielded
an official public post caption, but comment acquisition was not established.
JD's public recommendation pages yielded review text; dates and complete SKU
review histories are not established. Public Reddit discussion excerpts required
the current host's web reader; local JSON/RSS/browser attempts were blocked.

Host-web output may be cached, partial or unavailable in a future backend. Preserve
the actual response and original URL with `host_web_reader`/`host_search_excerpt`
and excerpt scope. Never relabel these as successful local HTTP downloads.

The reviewed MediaCrawler repository depends on authenticated browser state and
explicitly restricts commercial use; it was not bundled or run. ScrapeCreators
and last30days' Bright Data Amazon path require external service credentials and
potential charges. They remain candidates, not verified integrations. No private
cookies, paid API calls or sign-in workflows were used in this verification.

For X, Douyin, Xiaohongshu, Taobao, Pinduoduo, SHEIN, Temu, TikTok Shop, Zhihu and
Weibo, the run did not establish their requested user-comment acquisition. Report
the actual narrower material, if any, and the missing path. Do not silently replace
platform reviews with a search snippet, company biography or generic homepage.
