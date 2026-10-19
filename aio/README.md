# AIO: weekly work and verification

The site already has canonical URLs, hreflang, structured data and a fixed 20-question core panel. Use the existing panel in `panel.json`; keep API answers and consumer UI answers in separate measurements. A crawler request, an HTTP 200 or a sitemap entry does not establish indexing or recommendation.

## Ten priority pages

`priority-pages.json` contains the English and Japanese home, pricing and three primary use cases. Generate a review without creating keys, rendering, posting messages or calling an LLM:

```powershell
python tools/aio_review.py --check-pages --out reports/aio-weekly
```

This checks GET responses one at a time. Google indexing remains `unknown` until the owner checks each URL in Search Console's URL Inspection. Record actual results in a local JSON file:

```json
[
  {"url": "https://render.janction.jp/", "indexed": true, "checked_at": "2026-10-15", "reason": "URL is on Google"}
]
```

That is a format example, not an inspection result. Pass your real file, together with a Search Console performance export:

```powershell
python tools/aio_review.py --gsc path/to/search-export.zip --inspections path/to/actual-inspections.json --out reports/aio-weekly
```

Absence from a performance export does not mean a URL is unindexed. Inspections older than 14 days are marked stale. Search Console Web performance includes AI features and cannot isolate AIO clicks; Bing/Google referral traffic also does not identify whether an AI answer caused the visit.

## Three verifiable use cases

The English and Japanese pages `/render-blender-without-gpu`, `/ai-3d-model-render` and `/ai-agent-generated-3d` link recorded inputs, settings, dates, outputs and replay commands. `/benchmarks.json` exposes the same evidence under `use_cases`; the text versions include it too. An unrecorded round-trip duration stays null. Historical GPU times are observations, not promises; estimated prices use the current configured rate before rounding, credit and outcome ceilings.

## Entry to first successful render

Public pages retain a source category and public landing path in sessionStorage for a 30-minute attribution window. There is no visitor ID, cookie or stored full referrer URL. Do Not Track and Global Privacy Control disable capture. `/start` attaches this optional label when it creates a key; malformed/private paths are discarded by the API.

The existing `tools/aio_weekly.py` JSON now includes `acquisition`, and its normal weekly summary shows source -> first successful render and success with the user's own input. It counts new external API keys, not people or visit conversion. Tests/monitors and completions after the reporting window are excluded. Historical clients, opt-outs and untracked MCP connections remain unattributed. No additional schedule is installed.

## Obtain one genuine external example

The account owner chooses a Blender user or MCP developer and sends an invitation after reviewing it. Suggested text:

> Please try JANCTION Render with one model or scene you are allowed to share. The examples above include reproducible inputs and measured outputs. Could you record whether upload, preview, price confirmation and download worked, plus any confusing steps? An honest report, including failures, is useful. Publishing a review is optional; we will ask your permission before naming you or linking your work. Please disclose any free credit or other compensation.

After the person consents, record the public URL, author, date, input/settings, observed result and any compensation disclosure in the existing outreach records. Self-published company articles and pending directory submissions do not count as independent reviews. No invitation has been sent and no external review is fabricated by these changes.

## DeepSeek (2026-10-19)

DeepSeek has its own search engine with a public Search / Fetch API (2026-10-17) and an agent harness (`dsh`) whose MCP client takes the existing `/mcp` with a Bearer key. `tools/deepseek_aio.py` measures the search side (42 queries in `aio/deepseek-queries.json`, brand / generic / compare / problem, en / ja / zh), fetches the priority pages through DeepSeek's Fetch API and, with `--ask`, scores deepseek-flash's answers with the same `judge` as the other engines. It needs `DEEPSEEK_API_KEY` (env/aio.env); without it, it writes an `unverified` report and never claims a listing. One full run costs about $0.05 (Search and Fetch are $0.75 per 1,000 successful calls). `tools/aio_ask.py --engines deepseek` runs the governed question sets against the DeepSeek chat API (no web search on that API, so `searched` stays false). The connection guide is `/deepseek-blender`; the API bridge is `examples/deepseek_tool_calling.py`. Details and the open items: `docs/80_DeepSeek対応_2026-10-19.md`.
