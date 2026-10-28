# Changelog

## 0.4.204 - 2026-10-29

- The legal notice (Act on Specified Commercial Transactions, /legal and /ja/legal) states the unit of the per-job spending cap: it applies to the whole render request, however the service splits it internally, and a request above the cap is not accepted and no fee is charged for it (wording approved on 2026-10-29).

## 0.4.203 - 2026-10-29

- A spending cap applies to the whole render request. The per-job cap (3,000 JPY by default) is now checked against the request's total hold, however the service splits a long final into parts internally; splitting never increases the cap and paying more does not lift it. The estimate (decision, cost.within_caps, next), the submission (403 spend_cap_exceeded before any 402) and the restart after a payment use the same rule (decision.cap_reasons). The per-part check of 0.4.195 is withdrawn.
- robots.txt no longer disallows /mcp (the MCP endpoint is the agents' regular entrance; Cloudflare's AI Crawl Control had counted Claude-User's /mcp calls as violations) and allows the public read-only JSON under /v1 (/v1/pricing, /v1/capabilities, /v1/health, /v1/outcomes).
- llms.txt (English and Japanese) explains how to pay: card registration through card_offer.link (nothing is charged, it adds free GPU time), top-ups through billing(topup_yen=N) and the Pay panel on /start, auto top-up and monthly plans in billing(), and what the 402 carries.
- billing() and GET /v1/me say low_balance when the credit is below a threshold (JR_LOW_BALANCE_YEN, 100 JPY by default) after the welcome credit; the MCP reply adds one line to next.
- Public pages and llms.txt are cacheable for 30 minutes at the CDN (public, max-age=1800, stale-while-revalidate=3600; JR_HTML_MAX_AGE); the deploy purges the cache. API responses stay no-store.
- Every monitoring and verification tool identifies itself with User-Agent janction-internal/<tool>, so Cloudflare analytics can exclude JANCTION's own traffic with one filter.
- The FAQ, /pricing, llms.txt, facts.json, /for-teams and the README say the same thing about caps: the cap set for a render request applies to the whole request, however it is split internally.

## 0.4.202 - 2026-10-28

- Prices, limits and retention have one source: pricing.yaml in the repository. The README, the PyPI description, the extension and plugin descriptions, the skill and the stdio tool descriptions are generated from it (tools/terms_sync.py), and a CI check fails when a generated file is stale, when a published file still says 'free beta', '10 GPU-minutes', a 500 JPY welcome credit, 'from 500 JPY' or a 240-frame limit, or when the version numbers disagree. scripts/check_live.py compares the live site, PyPI and the public README with the same file and tells a stale CDN copy from a stale origin.
- Every estimate carries decision: can_execute, blocking_reasons, required_actions and runs_after_payment, decided in one place. cost.within_caps, the MCP next text, the payment wording, /start and the preflight checks all read it, so a render blocked by a spending cap is no longer described as 'top up and it runs'. The per-job cap applies to each part's hold and the per-day cap to the sum of the parts; decision.caps shows the arithmetic.
- Estimates say how sure they are with one word (high / medium / low) in both calibration and uncertainty. The long max_frames_per_job_deprecated note is gone from every reply; a short note stays on /v1/pricing, facts.json and capabilities.
- scene_url accepts GitHub and Hugging Face file pages: /blob/ links are read as the raw file, and a link that returns a web page (HTML) is refused with the reason and the fix instead of 'the GLB is damaged'.
- A script or 3D file that does not set a render engine renders with Cycles whichever way it was sent. Before, a scene sent by scene_url rendered with Cycles and the same scene after scene_info with EEVEE (Blender's start-up value). scene_info says where the engine comes from (engine_source).
- preset='product' and turntables frame the product: oversized companions (stands, floor boxes, environment domes), objects named like backdrops and empty objects are left out of the framing, and the camera distance follows the object's width and height instead of its bounding sphere.
- Blender's deprecation notices (Material.use_nodes and the like) no longer appear in the text of a failed script; they come back as warnings marked as not the cause.
- facts.json: free_tier says what is free (model) instead of status / charged_yen; release_url points at this service's changelog (the PyPI version page can lag a deploy), with pypi_url beside it.
- Guides: Related lists five nearby guides instead of all of them, the top page groups the guides by topic, Japanese pages carry a one-line glossary (試し描き = preview, 仕上げ = final render, 鍵 = API key, 道具 = MCP tool), every page has its own OG image (/og/{lang}/{slug}.png), ChatGPT is connected the same way everywhere (Plugins > Add > Create plugin), and /products names the current MCP calls (preset='product' / 'turntable') in both languages.

## 0.4.201 - 2026-10-28

- A .blend export whose script runs out of time now says where the script was. When the scene built so far is returned, info.partial_at gives the line of the script that was running and how many objects had been built. When nothing could be saved because the script was inside one long operation, failure.line and failure.source_line name that line, and log.txt shows it.
- What a .blend export script prints is kept even when the export is stopped at the time limit (it used to be lost with the rest of the output).
- A job stopped at the time limit always has a log.txt now. When Blender printed nothing before it was stopped, log.txt says so and gives the error, instead of the download answering 404.

## 0.4.200 - 2026-10-28

- The new page design and the studio layout of /start that went out with 0.4.197 are withdrawn again (they were merged, then carried into production by the 0.4.198/0.4.199 deploys): every page is back to its previous look, /start is the previous form, and the studio only appears with JR_START_V2 set. Nothing else changes.

## 0.4.199 - 2026-10-28

- Preview sheets now write camera names in Japanese, Chinese and Korean with a CJK font (Noto Sans CJK) instead of empty boxes.

## 0.4.198 - 2026-10-28

- POST /v1/jobs/{id}/cancel now cancels a job, the same as DELETE /v1/jobs/{id}. The API description had listed it, but the path answered 404.
- Camera names (camera, cameras) and orbit_target are taken as Blender writes them, for example 'Camera (1)', a name in Japanese or 'Cam#2', instead of only letters, digits and . _ -. Only control characters and names over 255 bytes are refused.
- For a finished multi-camera job, the suggested next render and the saved recipe use the frame that was rendered, so they no longer fail with 'frame_end must equal frame_start'. A suggestion that cannot be built no longer turns the whole next-actions call into an error.
- The start page forgets a scene and a render that have passed their storage period and asks you to add the scene again, instead of showing a general error the next day.
- Render workers switch to new service code by themselves between jobs after an update, so a render in progress is never cut; /v1/health shows each worker's version and stale_workers.

## 0.4.197 - 2026-10-28

- New look for every page: dark background, orange accent, a fixed header (Products, Examples, Pricing, Benchmarks, Facts, language, Try free) and a footer with the full site map. The top page follows the agreed layout: the original headline and wording, a studio still rendered on JANCTION (the script is /samples/hero_studio.py), a 'works with' strip, the four steps as cards and, when the night batch has rendered them, three real examples; the detailed tables follow. /start is now the studio layout (the same form as the jr-studio-demo mock: left rail, drop zone that previews at once, result with finishing options, works, settings); ?ui=v1 keeps the previous form and JR_START_V2=0 restores it. Content, URLs, structured data and llms.txt are unchanged.

## 0.4.196 - 2026-10-28

- Failed and finished jobs now keep the last part of Blender's output as the artifact log.txt (GET /v1/jobs/{id}/artifacts/log.txt), which the API reference had listed all along without it ever being written: on 10/28 an agent waiting for a .blend export asked for it 18 times and got 404 every time. A script failure now also carries source_line and source_context (the failing line of the script as received, with two lines around it) next to the line number, so an agent that rewrites its script between runs can find the line. A .blend export that runs out of time says why the partial save before the limit could not help either.

## 0.4.195 - 2026-10-28

- The browser page /start has a studio layout behind a flag (JR_START_V2, off by default; open /start?ui=v2 to see it, ?ui=v1 for the previous form): a left rail (Render, Works, Settings), a drop zone that starts the free preview the moment a file lands, the result on the stage with the finishing options beside it, a Works view listing this key's previews and finals, and a Settings view (key, credit and top-up, connected AIs, email on completion). The rendering engine, prices, 402 flow and measurements are the same code as before; only the layout changed.

## 0.4.194 - 2026-10-28

- The top page (/ and /ja/) was rebuilt around what the service does today: a 4-step 'how it works' (send, preview with a verdict, estimate, final), the main apps to connect from with the full list on /blender-mcp, all 13 MCP tools including render_import_file, a free-key / paid-key table (previews, finals up to 4K, .blend size, how long files are kept) and the guarantees for an agent that pays (price before running, spending caps, Idempotency-Key, fixed-price outcomes). The long 'what is' paragraph, the wall of 60 guide links and the 20-row connect table are gone; the guides fold under one line. Table cells now wrap long commands on phones.

## 0.4.193 - 2026-10-28

- A preview or final of a scene whose last run already failed in a way that repeats every time (a script error, a Blender API change, a check in the script, a missing file, an unreadable file) is refused before it reaches a GPU, with 422 `scene_failed_before` (agent code `INVALID_SCENE` / `FIX_INPUT`), the earlier `failure` and the job id. Nothing is queued or charged. It goes through when the scene has rendered before with the same Blender version, when files were added to the scene after the failure, with another `blender` version, after 24 hours, or with `rerender=true`. Time-outs, memory limits, camera errors and failures on our side are not refused. On 10/28 a /start user's scene failed to be read three times (a GLB that was not sent) and two finals of the same scene were then started and failed at the same line.
- The remote MCP passes `failure`, `failed_job` and a next step for this refusal.

## 0.4.192 - 2026-10-28

- Estimates (`/v1/estimate`, `render_estimate`) and the pre-render check (`preflight`, also inside `scene_info`) now compare a long final that runs as parts with the per-job spending cap part by part, which is how the render itself is checked. They used to compare the hold for the whole range, so a 1,688-frame 1080p animation that the service then rendered as 7 parts was reported as `SPEND_CAP` "blocked". The per-day cap is still compared with the hold for all parts.

## 0.4.191 - 2026-10-28

- A bpy script that loads a file that was not sent with it is now reported as `MISSING_TEXTURE` / `SCRIPT_FILE_NOT_SENT` (send the file; do not remove the loading step) in two more cases: `bpy.ops.import_scene.gltf` answering "Please select a file" because the path does not exist, and `bpy.data.images.load` answering "Cannot read 'name.png': No such file or directory" (without the word "file"). On 10/28 six /start jobs from two outside users failed this way; the first was reported as a generic script error and sent to the automatic script fixer, the second as "Blender could not open the scene file".
- Every failure seen in production so far (184 jobs) and a set of likely ones were run through the failure classifier, and the cases that got generic, wrong or raw text now say what to change: scripts that the sandbox stops, operators that need Blender's window (`poll() failed, context is incorrect`), `input()`, operators from add-ons that are not enabled, `None` objects (no active object without a window, or a material without a node tree), `MemoryError` (RAM, not GPU memory), and Blender 5 changes that were all answered with the same material advice: the compositor (`scene.node_tree`), video output (`FFMPEG`), AgX look names, `BLENDER_EEVEE_NEXT`, `action.fcurves`, node options that became input sockets, and Principled BSDF inputs renamed in 4.0. Other values that do not exist now point to the list of accepted values in the error.
- A `.blend` saved by a newer Blender is no longer reported as "Blender crashed while reading the scene"; it suggests `blender='5.2'`. A crash in the middle of rendering is no longer called a crash while reading. A CUDA fault, frames that came back without an image, and a failed copy of the results out of the render container are explained instead of returning the raw message; as before, these three, and a full disk, are not charged.
- The /start script fixer records an `aifix` event when it fails with an exception (for example a rejected API key), and the morning summary lists it under things to act on. On 10/28 the fixer failed three times with 401 and left only a traceback in the server log.
- The morning summary's payment-failure line (checkout, auto-charge, subscription) read events through the failure report's filter, which keeps only five other event types, so it never appeared. It now reads those events directly.

## 0.4.190 - 2026-10-28

- `scene_info` (remote MCP and stdio) no longer answers "still queued" for a read that a worker has already started. A queued read still says "still queued"; a running one says "reading the scene now", and after 20 s it carries the time left until the read limit from 0.4.188 ("still reading the scene after 50 s; it stops at the 120 s limit at the latest"). Both servers share `mcp_common.info_pending_hint`.
- The operator's daily scorecard now ends each day at the day's end: jobs and keys created after it (the next morning, before the report is sent) were counted in the previous day.
- The operator's morning report and the daily scorecard line show top-ups (what customers paid) separately from the credit used by renders; they used to show only the latter as "sales".
- 0.4.189 is used by a separate change in progress.

## 0.4.188 - 2026-10-27

- Reading a scene (`kind=info`) that runs out of time: /start heads the message with `failure.reason` ("the scene took more than 120 s to build (nothing was rendered)") instead of the worker's raw "render exceeded the 120s limit", which read like a render failure; the guidance underneath was already specific. The failure is now `retryable: false`, matching its own advice that sending the same scene again times out the same way.
- A read that has run for 20 s or more reports the time left until its limit ("still reading the scene after 90 s; it stops at the 120 s limit at the latest") instead of "about 5 seconds" until the timeout, so agents stop polling every 5 seconds.
- On 10/27 an outside /start user sent the same heavy bpy script three times; each read stopped at 120 s (not charged).

## 0.4.187 - 2026-10-27

- Scripts that set a sky texture to `'NISHITA'` now render on Blender 5 with `'SINGLE_SCATTERING'`, the same sky model under its Blender 5 name (and `dust_density` becomes `aerosol_density`). Rendered side by side on 10/27, Blender 4.5 NISHITA and Blender 5.0 SINGLE_SCATTERING differ by 1 to 2 levels out of 255 in the sky's average color. Until now such scripts were rendered again on Blender 4.5, which failed when the same script also used Blender 5 material code (10/27, from ChatGPT). The earlier mapping to `'MULTIPLE_SCATTERING'` (10/19) changed the sky's color and was not used.
- The fix also finds `sky_type = 'NISHITA'` inside statements joined with `;` on one line.

## 0.4.186 - 2026-10-27

- Dependencies (dependabot #101, which also covers #81): mcp / mcp-types 2.3.0, fastapi 0.162.0, starlette 1.9.0, anthropic 2.3.0 (the /start script fixer's `beta.messages.create` arguments and the response fields it reads are unchanged in 2.3.0), and patch updates.
- The stdio MCP server now also reports the app that started it on the MCP SDK 1.x (FastMCP takes `call_tool` at start-up, so 0.4.185's wrapper did not run there; the name is read through `get_context()` inside the tool instead). Checked on mcp 1.28.1, 2.2.0 and 2.3.0.

## 0.4.185 - 2026-10-27

- The stdio MCP server (`uvx janction-render`, `npx -y janction-render`) now tells the service which app started it: the `clientInfo.name` from the MCP handshake goes into `X-Client` as `mcp/<app> <version>` (it was `mcp <version>` for every app). Nothing else changes.
- Usage counts: keys labelled `dsh…` (DeepSeek Harness connected with an API key, whose requests carry only a Node user agent) count as DeepSeek Harness, and Sesame is named in the public usage stats.
- The per-key usage spike alert leaves out keys that paid on a Stripe checkout page in the last 24 hours (a person paying is not a stolen key); automatic top-ups still count. On 10/27 it fired for a new customer from Cursor who had paid twice.
- The setup guides for Kimi Code, OpenCode, Qwen Code and Copilot CLI also show the way without uv (`pip install janction-render`, then `janction-render connect <app>`). OpenCode 1.19.4 was checked on a real install: `opencode mcp auth` and `opencode mcp list` (connected).

## 0.4.184 - 2026-10-27

- **A script that opens a file that was not sent now asks for the file.** A script stopped by `FileNotFoundError` (or a bpy loader's "Cannot read file") used to come back as a generic script error to fix, which could lead an agent to drop the loading step. It is now `MISSING_TEXTURE` (category `MISSING_ASSET`) with subcode `SCRIPT_FILE_NOT_SENT`, `missing_file` (the name in the script), the line, `fix_by: user`, and how to send the file (asset_urls, `POST /v1/files/{id}/assets`, `janction-render upload` or /upload). It is no longer offered for automatic script fixes.

## 0.4.183 - 2026-10-27

- **A partial .blend export is charged like other work.** The time of an export saved partway (0.4.182) comes out of the free allowance first; time past it is charged at the usual rate from the balance, only as far as the balance goes (no hold is taken when the export starts, it never goes negative, and keys without a balance still get the file). A finished export stays free.

## 0.4.182 - 2026-10-27

- **A .blend export that runs out of time returns the scene built so far.** When the script of `output="blend"` does not finish within the time limit, the worker saves the scene as built up to about 85% of the limit and the job is done with `partial: true` and a note, instead of failing with nothing. That time counts against the free allowance (a finished export stays free). An export that times out without a save now says the scene took too long to build, not to lower samples.

## 0.4.181 - 2026-10-27

- Qwen Code: `qwen-extension.json` at the repository root (read before `gemini-extension.json`) makes `qwen extensions install https://github.com/JasmyLab-JANCTION/janction-render` add the MCP server (`?src=qwen-extension`, `httpUrl`) and the workflow skill. `janction-render connect qwen` installs it (`:janction-render --consent`, falling back to `qwen mcp add --transport http`).
- OpenCode: `janction-render connect opencode` adds a remote entry under `mcp` in `~/.config/opencode/opencode.json` (`opencode.jsonc` when present); sign in with `opencode mcp auth janction-render`.
- GitHub Copilot CLI: `janction-render connect copilot` adds the server to `~/.copilot/mcp-config.json` (`$COPILOT_HOME` when set) with `"tools": ["*"]`; sign in with `/mcp auth janction-render`. The Claude Code marketplace in this repository also installs in Copilot CLI.
- Guides /opencode-blender, /qwen-code-blender and /copilot-cli-blender, rows in the connection tables, llms.txt and README. The app compatibility table now lists Cursor as verified (an outside key rendered a 792-frame animation on 2026-10-27) and adds Kimi Code, Qwen Code and Copilot CLI as not yet verified by outside use.
- Keys from Qwen Code (OAuth name `Qwen Code MCP Client`) are counted as `qwen-code`. `tools/unknown_apps.py` lists the client names behind "MCP (other apps)" in the public stats.

## 0.4.180 - 2026-10-27

- Kimi Code (Kimi K3 and other models): `kimi.plugin.json` at the repository root makes this repository a Kimi Code plugin. `/plugins install https://github.com/JasmyLab-JANCTION/janction-render` adds the MCP server (`?src=kimi-plugin`) and the workflow skill. Without the plugin: a `url` entry in `~/.kimi-code/mcp.json`, then `/mcp-config login janction-render` (OAuth).
- `janction-render connect kimi` writes that entry (`$KIMI_CODE_HOME/mcp.json` when set).
- New guide /kimi-code-blender (also /kimi, /integrations/kimi), and Kimi Code rows in the connection tables, llms.txt and README.
- Keys and jobs from Kimi Code are counted as `kimi-code` (its OAuth name is `kimi-code (<server name>)`), and "Kimi" is a choice for where you heard about the service.

## 0.4.179 - 2026-10-27

- Previews and finals without an `engine` now use the scene's own engine (read by scene_info): an EEVEE .blend renders with EEVEE instead of Cycles. Pass `engine='cycles'` or `engine='eevee'` to choose. On 10/27 an EEVEE scene from /start was previewed with Cycles and ran out of its 120 seconds; it would also have looked different from the scene. Preflight's `ENGINE_DIFFERS` now appears only when Cycles is asked for an EEVEE scene.
- Fixed: a .blend saved with video output (FFmpeg) stopped the worker's setup at the output format (Blender 5 accepts no PNG while the output kind is video), so the requested samples, resolution and the preview time limit were never applied and Blender rendered with the file's own settings (4096 samples on 10/27, 120-second timeout). The output kind is switched to images first (`JR_MEDIA_TYPE_IMAGE` in the log).
- Scripts: popup and dialog calls (`window_manager.popup_menu`, `invoke_props_dialog` and similar) are skipped like the script's own render call; Blender crashes on them without a window (exit 139), and a try/except in the script cannot catch it.
- A script that crashes Blender (exit 139 while running it) is reported as `SCRIPT_CRASHED` with what to remove, instead of `SCENE_READ_FAILED` with advice to re-save the file in Blender 5.0.

## 0.4.178 - 2026-10-26

- The MCP billing tool (remote and stdio) dropped the `card_offer` of `/v1/me`: an agent asking for the balance of a key whose free time was used up never learned that registering a card (no charge) adds free GPU time. The reply now carries `card_offer` and `next` says to tell it to the user first. From 10/12 to 10/26, 8 keys that got the offer through `/v1/me` (CLI and agents) registered none.
- CLI: `balance` prints the card line on stderr (and `card_offer` in its JSON); `estimate` prints the pricing sentence when a card or a top-up is needed; on a 402 with a card offer, the card line comes before the top-up link.

## 0.4.177 - 2026-10-26

- /start, the panel shown when a render waits for payment (402 with a held order): when registering a card covers the render, the heading says it can be rendered for free and the main button is "Register a card and render for free" (the paid amount stays as a second button); otherwise the heading says how many JPY are missing and the main button pays the top-up amount, with the first top-up bonus when there is one. The card page is opened in a tab created on the click, so a popup blocker does not stop it. The card offer was in the 402 body but the panel never drew it: 7 web keys that hit a 402 since 10/19 never saw it.
- Fixed: after paying, the panel kept saying "waiting for the payment" because the held order then reports the job's own status (queued, running, done), not started; the result now appears as soon as the job is done. A failed order (still short) shows its reason.
- Payment links styled as links (`<a class="b">`) now look like the other buttons.
- The price line under the main button (`/v1/estimate` pricing) names the free card path for keys that can still get it, as the MCP final offers already did.
- New browser events `card_offer_seen` (the card offer was drawn on the page) and `free_short_shown` are recorded; `free_short_shown` from 0.4.176 had been dropped by the event allowlist.
- A payer on the Japanese /start gets Japanese payment pages end to end: the top-up chooser opens in Japanese, a checkout page is reused only in the same language (`checkout_sessions.lang`; earlier rows count as English), `POST /v1/billing/checkout` takes `lang`, and the panel's pay button creates a Japanese checkout on the click instead of the English one the 402 made. Before, picking 100 JPY on the Japanese chooser reused the English page from the 402 and the return page was English.
- `tools/stripe_test_local.py --set JR_NAME=VALUE` passes flags to the local receptionist without touching the env file that holds the test key.

## 0.4.176 - 2026-10-26

- A free short version, behind the switch `JR_FREE_SHORT` (off by default; with it off nothing changes). When a video final does not fit the free GPU time left, `POST /v1/estimate` and the MCP estimates (render_estimate, the follow-up after a preview, the final offers) add `cost.free_short`: the longest of 5, 4 or 3 seconds at up to 1280x720 (same samples) that the receptionist would run for free, with the frame range and size to send. /start shows it as a second button under the paid main button, and the MCP pay sentence offers it as a second path; the render is shortened only when the user picks it. Submitting a job does not search for it.
- `tools/stripe_test_local.py` passes the other `JR_` values of its env file to the local receptionist.

## 0.4.175 - 2026-10-26

- With `JR_TOPUP_SHORTFALL` on (minimum top-up 100 JPY), the pricing page and /start said that a top-up from 100 JPY opens 5 GB .blend files: the page-wide rewrite of "from 500 JPY" to the minimum top-up also hit the paid-key condition, which is 500 JPY or more paid in total (`entitlements.paid_min_yen`). Those sentences, the estimate note and `purchase_required` for sizes above 1920x1080, and the per-image time note now say "500 JPY or more in total" and are not rewritten. The top-up page opened from the 5 GB button shows only amounts that reach that total (no 100 JPY tile, no card registration). The switch was on for about 3 minutes (13:52-13:55 JST) and is off until this is deployed; no checkout was created in that window.

## 0.4.174 - 2026-10-26

- Pay only the shortfall, behind the switch `JR_TOPUP_SHORTFALL` (off by default; with it off, prices and every page are unchanged). When on, the minimum top-up is `JR_TOPUP_SHORTFALL_MIN_YEN` (100 JPY) and the checkout made by a 402 rounds the shortfall up to 100 JPY (68 → 100, 158 → 200, 501 → 600) instead of 500 / 1,000 JPY steps. Web, MCP and the pricing, terms and commerce pages read the same value; the estimate carries `cost.topup_yen` so the sentence before the render names the amount the 402 will ask for. The held order of a 402 still starts by itself after payment, once. A checkout created before the switch keeps its amount, and a key that has paid before is still offered 2,000 JPY.

## 0.4.173 - 2026-10-26

- Removed the internal 240-frame part size from current public guidance, plugin instructions and integration metadata after a live Claude search answer misread it as the user-facing job limit. The supported limit remains 3,000 frames per instruction, with automatic internal splitting under one job id.
- Corrected the GitHub Action metadata that still described finals as limited to 240 frames per job.

## 0.4.172 - 2026-10-26

- Removed obsolete numeric terms from current pricing and AI-discovery documents, including correction sentences that search systems could retrieve without their surrounding negation.
- `llms.txt`, facts, pricing and capabilities now expose only current values plus a current-source policy; historical commercial terms stay in the changelog.
- Added the current welcome credit, metered price and frame limits directly to the ChatGPT plugin description.

## 0.4.171 - 2026-10-23

- The pricing page now labels itself as the current authoritative terms and links directly to the same machine-readable pricing contract. Its modification date and the site-wide crawl validators were refreshed after verifying the live 100 JPY plus 400 JPY welcome-credit terms.
- The English and Japanese pricing, no-GPU guide, facts and llms.txt URLs were resubmitted to IndexNow. Search snippets that predate paid use are stale; the live page and `/v1/pricing` are the source of truth.

## 0.4.170 - 2026-10-23

- The moment of payment after a preview: the next step now says one of four things (covered by the free time / about N JPY from the credit / a card registration that costs nothing covers it / a top-up of N JPY covers this render and about M more like it) instead of "it does not fit today, use fewer frames or wait for the reset" on a key that has credit. quota_left_today says what it applies to (previews only once the welcome credit is over; finals are paid from the credit), render_estimate uses the same wording, and final_offers carry mode card_needed when the card bonus covers the job.
- render_info: the diagnosis no longer fails on a zero balance alone, separates previews (free seconds left today) from finals (credit), reports "N lanes on M GPUs", and adds connection_ok / render_ready / paid_final_available and tell_user_ja. The stdio render_info no longer embeds the whole of /v1/me (webhook signing secret, billing links). /v1/me carries card_offer only when the balance is 0.
- environment='compare': the reply shows one frame in 4 lights (frames [1] plus variants), show_user asks the user to pick one, the final offer needs environment=<the pick> (a placeholder is refused by the server), and the critic no longer suggests hiding the HDRI in a compare sheet. Every preview also returns show_user_ja.
- No "whole animation" offer for a scene with nothing animated and the default 1-250 frame range; a still comes first.
- jr_assets.import_model removes Blender's untouched startup cube before importing, and the preview critic reports default_cube_left (severity fix when the imported objects sit inside the cube, which made the cube the only thing in the render).
- Card registration that does not qualify for the free GPU time (a prepaid card, or a card already used on another key) now keeps the saved card and answers with a top-up link that uses it (card_kept, topup_link; the return page shows the button), instead of removing the card. No free time is added in these cases, as before. Top-up checkout pages pass the key's Stripe customer so a saved card is offered.

## 0.4.169 - 2026-10-23

- Measurement only, nothing visible changes: the /start page now records how long the finish button was on screen before a visitor left without pressing it, whether the button was scrolled into view, and whether the settings were opened. No key, IP address or personal data is recorded, as before.

## 0.4.168 - 2026-10-23

- What a bpy script prints now comes back even when the render succeeds: script_output on the job (GET /v1/jobs/{id}, render_status) and in scene_info, the last 300 lines. Scripts no longer need to raise an error just to read a value such as a camera projection. Over MCP, failures also carry line, check and auto_fix.

## 0.4.167 - 2026-10-23

- When a script stops itself with its own check (an assert, or a raise at the line that failed), the failure now says so: code SCENE_QA_FAILED with the check's message and line, and auto_fix false, so the check is not removed just to get an image. When Blender's startup line was mixed into an error, the line shown is now the one that actually failed.

## 0.4.166 - 2026-10-22

- Groundwork for JANCTION Storage re-renders: when Storage asks for a re-render, the same look settings (product shots, turntables, studio light, multiple cameras) come back exactly, "render again" always renders instead of reusing earlier frames, and textures stored next to a .blend in Storage are delivered with it, including ones Storage found in another folder. Off until Storage switches it on; prices, limits and the results of renders sent with an API key are unchanged.

## 0.4.165 - 2026-10-21

- Previews and finals over the HTTP API take background: grey (default, unchanged), white (only what the camera sees directly turns white; lighting and reflections stay on the studio light) or transparent. It needs an environment preset such as preset='product'. The MCP server's directory listing is titled JANCTION Render.

## 0.4.164 - 2026-10-21

- A render whose estimate fits your free GPU time no longer asks for a small credit hold when the key has no credit: it runs free, and if it runs a little past the free time we cover that part (up to 50 JPY). On free time, a single heavy frame that runs past the time limit is drawn again within your welcome credit left, instead of failing.

## 0.4.163 - 2026-10-21

- Security: repeated failed sign-ins from one network are paused for a few minutes (429 auth_locked with Retry-After); requests without a key are not affected. Paid and long renders are no longer moved out of the extra sandbox layer when it fails to start; they are retried on another GPU worker at no charge.

## 0.4.162 - 2026-10-21

- Groundwork for connecting JANCTION Storage: a JANCTION Render key holder can let Storage start renders that continue a Storage project, without pasting the key into Storage. Off until Storage switches it on; prices, limits and paid-render approval are unchanged.

## 0.4.161 - 2026-10-21

- /facts.json lists use cases (the problem, who it is for, inputs, the first tool, the steps, what it is not for, and the guide page) so an AI can tell when this service fits a request and when it does not.

## 0.4.160 - 2026-10-21

- The web start page shows the free welcome credit and its expiry next to the balance, so a returning user no longer sees only "Credit 0 JPY".
- A size saved from an earlier visit that this key cannot render without prepaid credit (for example 4K) is no longer offered on the main button.
- Credit notes say whether the free credit is low or only expiring, and say the time left in hours when it is under two days.
- After the files expire, the start page and the recent-jobs list (render_status without a job, GET /v1/jobs?summary=1) still offer the settings of earlier finals; send the file again to render with them.

## 0.4.159 - 2026-10-21

- The CLI `balance` and `doctor` commands now report welcome/free credit, prepaid balance, holds, and the actual total available amount separately, so a key with card-granted free credit is no longer described as having zero usable credit.

## 0.4.158 - 2026-10-21

- A preview no longer runs at the sample count saved in a .blend when that count has keyframes or a driver: the requested samples are kept, and each preview frame on Cycles has a render-time cap, so a heavy scene returns an image instead of timing out.

## 0.4.157 - 2026-10-21

- Bumped every public page's sitemap and HTTP modification date after the site-wide stale-cache correction, so crawlers no longer see unchanged 2026-10-14 dates on affected guides.
- AI citation evaluation now fails answers that repeat obsolete 240-frame, 1,000-frame, free-beta, or daily-10-minute claims as current terms.

## 0.4.156 - 2026-10-21

- Added `Last-Modified` and content-derived `ETag` validators to every public HTML and negotiated Markdown guide so search and AI crawlers can detect replacements of stale cached pages.
- Marked every older changelog entry as a historical snapshot in HTML, Atom, and JSON, with a direct link to the current fact sheet.
- Expanded the authoritative machine-readable commercial contract with effective/verification dates and structured obsolete claims, including the former 240-frame, 1,000-frame, 1080p-only, and free-beta terms.

The live, per-version list is at https://render.janction.jp/changelog (Atom: https://render.janction.jp/changelog.xml). Versions are the PyPI releases of `janction-render`; the hosted service follows the same numbers.

## 0.4.155 (2026-10-21)

- Existing English and Japanese guides now answer the weak non-brand discovery questions directly: rendering FBX from four angles, rendering USD in a browser, batch and white-background product images, CPU-only school PCs, Python `.blend` upload and headless Blender from CI.
- The product-turntable guide no longer describes 4K as unsupported: free GPU time is limited to 1080p, while prepaid credit supports up to 4K.

## 0.4.154 (2026-10-21)

- The local MCP server (stdio) shows the same suggested next step after a finished render as the remote one, when the service turns it on.
- The Claude plugin description says "no sign-up", like the OpenAI one.

## 0.4.153 (2026-10-21)

- After a finished render, the service can suggest one next step and one alternative (with the time and price, and asking first for anything paid), and save the render's settings for next time (`GET /v1/jobs/{id}/next-actions`, `GET /v1/jobs/{id}/recipe`, `janction-render recipe JOB`). These are turned on step by step; nothing renders until you press or confirm.
- After `preview` and `render --wait`, the CLI prints a suggested next command on stderr when the service offers one; stdout stays the JSON result.

## 0.4.152 (2026-10-20)

- The web start page shows a preview as a draft: its save button names the draft size, and a line under the image leads to the full-size render (docs/81 §10).
- After sending a different file or a fixed script, the start page no longer reuses the earlier request's Idempotency-Key, which made the next render fail with `idempotency_key_reused`.

## 0.4.151 (2026-10-20)

- A failed final now says what was delivered: `delivery` (`total`, `delivered`, `not_delivered`, `files`, and `frames_not_delivered` or `cameras_delivered` / `cameras_not_delivered`). The status stays `failed`; the delivered files download like any result (view_url, `/artifacts/{name}`, `/archive`).
- MCP status replies (stdio and remote) carry `failure` (code, reason, recommended action, alternatives with estimates; without Blender's log lines) and `delivery`, instead of only the error sentence.

## 0.4.150 (2026-10-20)

- DeepSeek Harness (dsh) calls are recognized from the MCP client name, so renders started from dsh count as DeepSeek in usage statistics; other apps are unchanged.
- /deepseek-blender states who pays for what: DeepSeek tokens on your own DeepSeek key (it stays on your machine), GPU time on your JANCTION Render key. It also records the 2026-10-20 check of dsh's tool loop calling render_info and render_preview through the plugin.

## 0.4.149 (2026-10-20)

- A script that was already auto-fixed and is sent again (for example after an AI fixed a typo) keeps one copy of the compatibility helpers on its first line; before, each resend added another copy, and a new rewrite in a resent script that needed a helper already present was dropped.

## 0.4.148 (2026-10-20)

- Final renders with several cameras are planned like any other final: heavy angles go out one camera per part, and a part renders only its own cameras. Before, two heavy 1080p angles shared one 240-second part and could not recover after a timeout (docs/81).
- Before rendering, each frame or camera image is checked against the time limit (240 s on free keys, up to 1800 s on prepaid keys). If it clearly cannot fit, nothing is queued: 422 `estimate_exceeds_limit` (code `RENDER_ESTIMATE_EXCEEDS_LIMIT`) lists lower-resolution, lower-sample and prepaid options with their estimates. Settings are never lowered automatically. `render_estimate` / `POST /v1/estimate` return the same `feasibility`.
- A failed final now says which unit ran out of time, the limit, what was delivered, what was counted and the options (`failure.subcode`, `failure.alternatives`).
- A final that timed out without delivering anything is not charged and does not use free GPU time (up to 3 a day per key, `JR_TIMEOUTS_FORGIVEN_PER_KEY_PER_DAY`). The same settings are not rendered again after such a timeout unless something changes or `rerender=true`. Timeout retries per job are capped (`JR_JOB_RETRY_SECONDS_MAX`).
- Sending the same final again from /start or an MCP client while it is still queued or rendering returns that job instead of starting another (`duplicate_of`, code `RENDER_DUPLICATE_REQUEST`); `rerender=true` renders it again on purpose. REST calls without an Idempotency-Key still get a second job, marked `possible_duplicate_of`. /start no longer sends while a render is running.

## 0.4.147 (2026-10-19)

- DeepSeek: a connection guide at /deepseek-blender (DeepSeek Harness through the official dsh-mcp-client with a Bearer key, the DeepSeek API through function calling, the web chat through /start), rows in the connect tables, and the aliases /integrations/deepseek, /deepseek, /deepseek-harness. Verified with dsh 0.2.1-rc.2 against a local server (2026-07-28 revision, server/discover and tools/list, 12 tools).
- examples/deepseek_tool_calling.py bridges the MCP tools to DeepSeek function calling; render_final asks before spending GPU time.
- tools/deepseek_aio.py measures DeepSeek's own Search / Fetch API for 42 queries and the priority pages; without DEEPSEEK_API_KEY it reports "unverified". tools/aio_ask.py gains a deepseek engine.
- found_via accepts "deepseek"; public statistics name DeepSeek and DeepSeek Harness.

## 0.4.146 (2026-10-19)

- Removed the last stale search-snippet phrase, “240-frame cap per job,” from the animation guide metadata. It now states the 3,000-frame instruction limit and automatic 240-frame internal parts.

## 0.4.145 (2026-10-19)

- Every machine-readable discovery surface now carries one authoritative commercial contract derived from runtime settings. It explicitly corrects the recurring false claims that finals stop at 240 frames, that paid renders stop at 1080p, or that the service is still a free beta.

## 0.4.144 (2026-10-19)

- English and Japanese pages now expose the same connector choices, navigation targets, legal-payment fields and guide links. A full bilingual surface test prevents sections, CTAs, internal links and structured data from drifting again.

## 0.4.143 (2026-10-19)

- The missing-image warning comes first: Cycles' one line per missing image filled the warning list and pushed out the count and how to pack them.

## 0.4.142 (2026-10-19)

- Scenes whose compositor (Glare, Lens Distortion) ran on the GPU crashed right after the last sample on our workers. The compositor now runs on the CPU, with the same nodes and the same look.
- A .blend whose images were not sent rendered pink without a word. The result now warns how many images were not found and how to pack them.
- The gallery says which entries are examples made by the JANCTION team.

## 0.4.141 (2026-10-19)

- `storage_project` on `POST /v1/jobs` and MCP `render_final`: when saving to JANCTION Storage is on for the key, the result goes into that Storage project instead of a new one ("render again" from a Storage project continues the same project). Ignored otherwise.

## 0.4.140 (2026-10-19)

Keep going after a result (behind `JR_UX_GROW`).

- The web page lists up to five earlier finals whose scene is still kept; one press renders again with the same scene and settings, no upload.
- Under a finished final: render the same scene again with other settings (the settings panel opens), or a turntable video of it.
- An invitation to make a public page for the result; the public gallery is used only when the person ticks it, and only after a check.
- `GET /v1/me` carries `plan_hint` only for keys that topped up two or more times in 30 days and whose spend would buy more credit on a monthly plan.

## 0.4.139 (2026-10-19)

- On the web page, a button under a result that opens the "Before rendering" box (change the light, preview again, one frame, product shots, turntable, check the balance) now scrolls to that box when it is off screen. Before, nothing seemed to happen where the button was, and people pressed it several times in a row.

## 0.4.138 (2026-10-19)

- The MCP tool texts and the AI-app guide pages say it plainly: the price is shown before anything is rendered, final offers give each next render's time and price, a paid render runs only after the user approves it, and max_yen caps the charge.

## 0.4.137 (2026-10-19)

- JANCTION Storage link, off by default (`STORAGE_KEEP_ENABLED`): when it is on for a key, a finished job can be saved to JANCTION Storage (`POST /v1/jobs/{job_id}/storage/save`, only the key's own jobs; a "Save to Storage" button on the web result). The job status carries `storage` (state and link). Storage space is its own plan, separate from GPU time; if Storage is down, the render stays done and saving can be retried. Revoking a key unlinks it from Storage. With the switch off nothing changes.

## 0.4.136 (2026-10-19)

- A size above 1920x1080 on a key that has never bought credit is priced as `purchase_required` (top up from 500 JPY, then press again; up to 1920x1080 stays on free time) instead of "about 0 JPY from your credit". On the web page the main button opens the top-up options in that case.

## 0.4.135 (2026-10-19)

- With final offers on, the `final_estimate` of an MCP preview carries the list price and the fits-today answer of the first offer (it kept the one-frame values before).

## 0.4.134 (2026-10-19)

- MCP `render_preview` with final offers turned on no longer fails: building the offers read the key the wrong way. Whatever happens while building offers, the preview itself is now always returned.

## 0.4.133 (2026-10-19)

After a preview: the next step and its price.

- The estimate carries `pricing`: one of `free_time` (covered by free GPU time, nothing to pay), `credit` (about N JPY from your credit, nothing more to pay; the held amount is the ceiling), `topup_needed` (the shortfall, the minimum top-up and what stays afterwards; after paying, the held render starts by itself) or `beta`, with an English and a Japanese sentence. Credit is never called free.
- MCP `render_preview` (behind `JR_UX_MCP_PRICING`) returns `final_offers`: for an animation the whole animation (estimated over all its frames) and one frame as a still are separate offers; a still, several cameras and presets get their own. A range the scene does not report is never widened. Paid offers carry `requires_user_confirmation` and `confirm_with` (render_final arguments with `max_yen` set to the held amount and an `idempotency_key`).
- MCP passes the details of `spend_cap_exceeded` (403) and says not to raise caps.
- The web page (behind `JR_UX_START_CTA`, `JR_UX_START_DETAILS`, `JR_UX_START_RESUME`) shows one main button under a preview (finish the image, make the video of all frames, or finish every camera angle) with the estimated time and price, an optional settings panel (size, quality, frames, output) that re-estimates on every change, and, when credit is short, holds the render and starts it by itself after payment.
- The top-up page names the render that starts after the payment; the payment page links back to the web page.
- The preview check records the scene's frame range.

## 0.4.132 (2026-10-19)

- A script with `sky_type = 'NISHITA'` keeps its Nishita sky: it is no longer rewritten to `MULTIPLE_SCATTERING` (a side-by-side render showed a warm sky turning neutral). When no Blender version is asked for, it renders on Blender 4.5 automatically with the same look; when Blender 5 is asked for, the error explains both choices.

## 0.4.131 (2026-10-19)

- A script that uses `sky_type = 'NISHITA'` is accepted again. In 0.4.130 the line the service adds to translate it was refused by the upload safety check and counted as a strike against the key. The upload now also keeps the script as sent whenever one of its own fixes would be refused.

## 0.4.130 (2026-10-19)

Previews that stall are drawn again, and more old scripts run.

- A preview that stops before drawing anything (no samples, no output for a minute, not in a heavy step such as BVH or shader compilation) is drawn again once on another GPU worker. The stalled attempt is not charged and does not use free time; if it stalls twice the job fails as RENDER_STALLED, on our side and free.
- `sky_type = 'NISHITA'` (renamed in Blender 5) runs as `MULTIPLE_SCATTERING` on Blender 5, and `dust_density` as `aerosol_density`. The reply says the sky can look slightly different.
- Setting or linking the Principled BSDF `Subsurface Color` input (removed in Blender 4.0) is skipped instead of stopping the script; the reply says the subsurface tint can look different. Other subsurface settings are kept.
- A 3D curve's `fill_mode = 'BOTH'` is reported as a wrong value with the values a 3D curve accepts, not as a Blender version change.
- A script refused for a syntax error says why: cut off at its end, not a Python script, typographic quotes, or a code error, with `cause`, `next_action` and `agent_can_fix` in the API and MCP replies.

## 0.4.129 (2026-10-19)

Fewer failed scene reads and previews.

- A script that Blender 5.0 rejects because of an older API (for example `action.fcurves` or a video `file_format`) is now read again on an older Blender when the scene is first read, as previews and finals already were.
- Setting the output format to FFMPEG through a variable and reading `fcurves` from an action stored in a variable are now fixed on upload, like the direct forms.
- A script error that mentions FFMPEG is no longer reported as a video assembly failure on our side.
- A preview or final keeps the service's sample count even if the scene raises it again right before rendering (a render handler or per-view-layer samples).
- A render that crashes while drawing grease pencil inside the sandbox is drawn again once in the hardened container.

## 0.4.128 (2026-10-16)

Receptionist and agent workflow.

- An animation is checked frame by frame before it is marked done. Missing or unreadable frames and an isolated near-black frame now stop delivery with `verification_failed` instead of silently producing a broken video.
- Estimates say whether they are based on a completed contiguous test using the final render settings. The workflow asks for ten contiguous final-path frames and a fresh estimate before a long final render.
- The agent workflow preserves the scene's render engine and intended look unless the user approves a change, and verifies the exact frame count and output before delivery.

## 0.4.127 (2026-10-15)

Receptionist.

- llms.txt states the file size limits: `.blend` files sent in parts up to 1 GB on a free key and 5 GB on a key that has paid 500 JPY or more in total (saving a card alone does not raise it), other 3D files and scripts, and 100 MB per single request.
- Pages fit phone screens: videos and images shrink to the width, wide tables scroll inside themselves, and the menu and footer wrap.
- On /start, the next step after a first preview is written for the person reading it; the API and MCP replies keep the agent wording.
- The resumable upload operations (`/v1/uploads`) are described in openapi.json.

## 0.4.126 (2026-10-15)

Receptionist and client.

- Estimates and the billing reply give the daily free GPU time as the preview allowance (120 seconds) with what it applies to; they used to show the former 600 seconds a day.
- A 4K estimate on a key that has not bought credit no longer says free: it says prepaid credit is needed, and that 1920x1080 is free.
- An estimate for an unknown `scene_id` answers 404 `scene_not_found`, like creating the job.
- The `render_preview` and `render_final` tool texts name Blender 4.5, 4.2 and 3.6 too.

## 0.4.125 (2026-10-15)

Receptionist and worker.

- A script that sets or animates a light or camera value on the object (`light.energy`, `keyframe_insert("energy")`) gets the right fix: those values live on `obj.data`. It used to be told that an image was missing. Such a script is not rendered again on an older Blender.

## 0.4.124 (2026-10-15)

Receptionist and worker.

- Node inputs and outputs whose names changed between Blender versions (Distort / Distortion, Fac / Factor, Bright / Brightness, Z / Depth, Image / Background and Foreground) are looked up under the name the running Blender uses, so a compositor written for Blender 4 no longer stops on them. A script that still stops on such a name is rendered again on Blender 4.5, 4.2 or 3.6.

## 0.4.123 (2026-10-15)

Receptionist.

- On /start, a script that stops with an error is fixed by Claude: only the lines the error needs change, the page shows what was wrong and what changed, offers the fixed script to save, and reads the scene again. Scripts sent through an AI app (MCP or the API) still get the line and the fix in the reply, because that AI can fix them itself.
- llms.txt says that Blender 3.6, 4.2 and 4.5 can be named and that scripts written for them are rendered again on them automatically.

## 0.4.122 (2026-10-15)

Receptionist, worker and client.

- Blender 3.6, 4.2 and 4.5 run next to 5.0 and 5.2. A script that stops on Blender 5 because it uses an older API (for example `scene.node_tree` or `sequence_editor.sequences`) is rendered again on 4.5, 4.2 or 3.6 automatically, and the reply says which version drew it; the failed try is not charged.
- `blender="4.5"` (or `"4.2"`, `"3.6"`) picks one directly. A `.blend` still opens with the version it was saved in (5.0 or 5.2).
- EEVEE renders on every version (its engine name differs on 4.2 to 4.5).
- CLI: `--output blend` no longer asks for `--frames`.

## 0.4.121 (2026-10-15)

Receptionist, worker and client.

- `output="blend"` on a final render returns the scene the script or import built as one `scene.blend`, without rendering. Images from the upload and its assets are packed inside; text blocks set to run when the file opens are removed; the reply says it opens in Blender 5.0 or later.
- It uses no GPU and is free (it does not use the free time either), and it runs even while the GPUs are lent out. `render_download(only="blend")` and the CLI `--output blend` fetch just the file.

## 0.4.120 (2026-10-15)

Receptionist, client and docs.

- Files are kept normally 7 days for keys that have paid 500 JPY or more in total (24 hours for other keys); every page, llms.txt, facts.json, the MCP tool descriptions and this README now say it that way instead of "keys that have topped up".
- openapi.json and `/v1/capabilities`: 5 GB `.blend` uploads need 500 JPY or more paid in total; a saved card alone does not open them (former field names kept with a note). facts.json adds `saving_a_card_alone_unlocks_paid: false`.
- The Blender API guide says the OpenAPI document is published at `/openapi.json`.
- Terms, section 7: the Service is no longer called a beta; availability and response times are still not guaranteed.

## 0.4.119 (2026-10-15)

Receptionist and worker.

- Color looks: a look such as `'AgX - Medium High Contrast'` is kept as written; a look written for another view transform is changed to the name Blender 5 uses with the scene's view transform, or skipped when that view transform has no such look. 0.4.115 had removed the `AgX - ` prefix, which made those scripts fail.
- Scripts written for the Blender 4 compositor (`scene.use_nodes = True`, `scene.node_tree`) run on Blender 5: the compositor becomes a Blender 5 compositor node group, the Composite node its group output, and compositor nodes Blender 5 no longer has (such as MixRGB) pass the image through.

## 0.4.118 (2026-10-14)

Receptionist.

- The English /upload page no longer says a saved card opens 5 GB (it takes 500 JPY actually paid since 0.4.117).
- facts.json names the paid .blend limit `max_blend_upload_mb_paid`; the former name stays with a note for older readers.
- The morning report counts how often paid keeping was shortened for lack of space.

## 0.4.117 (2026-10-14)

Receptionist. **Free and paid keys (from 2026-10-14):**

- **Free keys send .blend files up to 1 GB; paid keys up to 5 GB, and their files and results are kept for 7 days (normally) instead of 24 hours.** A paid key is one that has paid 500 JPY or more in total: top-ups, auto top-up, monthly plans and USDC count; the free credit, the card-saving credit and bonuses do not. Saving a card alone no longer opens 5 GB for new keys.
- Keys that could already send 5 GB because a card was saved keep 5 GB. Keys that had paid before keep both 5 GB and 7 days.
- A .blend over the free limit (and within 5 GB) is answered with what it takes to send it: the current limit, the file size, the paid limit and a top-up link (413 `upload_limit`). On /start the top-up opens in a new tab and the page sends the same file once the payment is confirmed.
- A full refund or a chargeback makes new use free; data already kept stays until the expiry it had. A partial refund changes nothing.
- The pricing page compares free and paid keys; `GET /v1/me` reports the key's plan; the result page shows the actual expiry.
- When server storage runs short, paid keeping can be shortened; the operator is warned before that.

## 0.4.116 (2026-10-14)

Service.

- **Many jobs finishing at the same time no longer make the service pause for a few seconds:** reports from the render machines are recorded without holding up other requests.

## 0.4.115 (2026-10-14)

Receptionist.

- **Scripts written for a local Blender, or for an older Blender, now run as sent.** When a bpy script arrives, JANCTION Render skips the script's own render, image save, .blend save, file export and exit calls (the service renders and saves), skips viewport-only operations, and updates names that Blender 4 and 5 changed: the EEVEE engine name, old Principled BSDF inputs (Specular, Transmission, Clearcoat, Sheen, Emission and others), action.fcurves, removed EEVEE settings, auto smooth, material shadow mode, the output format setting and old color look names. Node names from a Japanese Blender UI are changed to the English names. Line numbers stay the same, and the reply says what was changed.
- A script pasted together with the text around it in a Markdown code block is taken out of the block and run.
- The morning report analyses failed jobs by cause.

## 0.4.114 (2026-10-14)

Site.

- **Three new guides in English and Japanese:** rendering a 3D model made with an AI generator (Meshy, Tripo, Rodin, Hunyuan3D, TRELLIS) into product shots and a turntable; five free ways to render 3D, compared; and Blender on an RTX PRO 6000 (96 GB) paid by the second, with measured times per frame. Related guides link to them.
- **The pricing page's structured data is complete** (product image, brand, and the current free-credit wording).
- The comparison with running Blender on your own cloud machine is worded in general terms.

## 0.4.113 (2026-10-14)

Site.

- **Every page was reviewed in English and Japanese.** Each guide opens with its answer paragraph, the home page opens with a one-paragraph definition, and every page carries structured data with the date it was last updated.
- **The security page says what is protected and how to report a problem**, and names the responsible person; the legal notice names the responsible person in both languages.
- **Pages say which Blender version renders each input:** a .blend opens with the version it was saved in (5.0 or 5.2); scripts and 3D files use 5.0 unless blender='5.2' is passed.
- **llms.txt states the welcome credit, the card-saving credit and the frame limit** in its opening paragraph.

## 0.4.112 (2026-10-14)

Receptionist.

- **llms.txt no longer puts the welcome-credit condition inside the top-up bonus:** "the first top-up counts 1.5x (bonus up to 500 JPY)" stands alone; the 100 JPY / 400 JPY condition belongs to the welcome credit.
- **The Japanese llms.txt states the current frame limit** (up to 3,000 frames per instruction in parts of 240, 1080p on free time and 4K on prepaid credit) instead of "240 frames at 1080p".

## 0.4.111 (2026-10-14)

Receptionist.

- **Parts of a job that already ended are never left in the queue:** a part that comes back after its job failed or was canceled is dropped instead of retried, and wait estimates count only parts of live jobs (two leftover parts had made the shown wait longer than it was).
- **The preview check no longer calls a low-key shot "dark":** a well-lit subject on a dark backdrop (a common product look) is left alone; a frame that is dark overall is still flagged.

## 0.4.110 (2026-10-14)

Receptionist.

- **A render stopped at its memory limit says it ran out of system memory (with the box size), not GPU memory,** and that finals get a larger box.
- **A scene read that runs out of memory says so,** with the memory limit of its render box, like previews and finals.
- **A scene read is reused only for the same Blender version:** a .blend read with 5.0 before it began opening with its saved version 5.2 no longer keeps answering with 5.0's warnings.
- **A preview or scene read that runs out of memory is no longer sent again to another GPU worker** (every worker uses the same smaller box for previews); only finals move to a bigger box.

## 0.4.109 (2026-10-14)

Receptionist and client.

- **Script errors are named for what they are.** A Python KeyError from a name that is not there is a script error, not a missing texture; a node looked up by its name in another language (for example a Japanese Blender's "プリンシプルBSDF") says to use the English name; a script that calls sys.exit says so instead of "unknown".
- **A scene that does not finish being read in time gets the right advice:** lower subdivision only when the script sets high levels; otherwise check for endless loops, sleeps or waiting for input.
- **A broken link to another .blend is reported** by the preview check (missing_library), and Blender's own bundled assets are no longer listed as missing files.
- **A .blend opens with the Blender version it was saved with** when no version is given (REST, MCP and CLI, as /start already did); if no worker has that version, it opens with the default and says so first in the warnings.

## 0.4.108 (2026-10-14)

GPU workers.

- Scene reads and previews run in a 16 GB render box and finals in the full 64 GB box; if the GPU server runs short of memory, render boxes are stopped first so the service itself keeps answering.

## 0.4.107 (2026-10-14)

Receptionist, GPU workers and MCP.

- A render that runs out of memory on a smaller GPU worker is drawn again on a worker with a bigger render box (64 GB); the lost time is not charged.
- Each key can keep up to 20 GB of scene files at a time; past it, an upload answers 507 storage_quota with how to free space (reuse a scene, wait for expiry, or erase).
- A compressed .blend that unpacks to more than 16 GB, unpacks over 100 times its size, or is damaged is refused at upload.
- After a key is revoked, its jobs' watch pages show nothing.
- render_status without a job id lists your recent jobs, so an agent in a new chat can find them; render_info includes a plain-words diagnosis (connection, key, credit, GPUs, last error).
- Webhooks carry event_id and schema_version 2 and are sent again with backoff when the receiver does not answer.
- Limits are listed in one shape (value, unit, applies_to, alternative) in /v1/capabilities, facts.json and openapi.json.
- Too-large answers point to the upload page; preview checks carry fix_params and fix_code next to the fix text.
- Uploads are checked off the main loop, so a large compressed .blend does not slow other requests.
- The first successful preview says how much free GPU time is left and, if available, that saving a card adds 400 JPY (nothing charged).
- Reading a scene that times out is not counted against free time; the same scene is not read twice at once, and a scene that timed out is not read again until it changes. The message says the scene took too long to build and points to heavy settings such as high subdivision levels.

## 0.4.106 (2026-10-14)

Receptionist and client.

- **3D files that Blender cannot open are refused at upload, with what to export instead:** an ASCII FBX (Blender reads binary FBX), an STL cut short, an Alembic in the old HDF5 format (Blender reads Ogawa), and a GLB, glTF, PLY or USD file whose header does not match its name. They used to wait for a GPU and fail inside Blender.
- **Compressed .blend files open with the right Blender version:** gzip files are read for the version they were saved with, and zstd-compressed ones open with the newest Blender available.
- **Jobs say which stage they are in:** `stage` is `rendering` or `assembling` while a job runs, so a long final that is joining its parts into a video does not look stuck. The MCP status shows it.

## 0.4.105 (2026-10-14)

Receptionist.

- **Many estimates at once no longer slow the service down.** Estimates are computed off the request loop, so twenty agents asking at the same moment do not hold up everyone else's calls.

## 0.4.104 (2026-10-14)

Receptionist and client.

- **Every guide's answer names the MCP URL.** The paragraph AIs quote ends with where an agent connects (https://render.janction.jp/mcp, remote MCP with OAuth) on every guide, not 9 of 39.
- **/start links to using it from an AI** (Claude, ChatGPT, Codex) next to the first-question tags.
- **`janction-render doctor` compares with the live version** and says how to update when a newer one is out.

## 0.4.103 (2026-10-14)

Receptionist, GPU workers and pages.

- **A render that runs out of memory says so.** When a render goes past the memory of its render box, the job fails as out of memory with what to lower, instead of reporting that your script failed; it is not retried.
- **A .blend saved by a newer Blender opens with that version.** The scene view tells which Blender saved the file and which one opens it, and /start uses it for reading, estimating and rendering; Blender's memory-cleanup lines are no longer shown as warnings.
- **/start and /upload take a file dropped on the dashed area,** and a file dropped elsewhere no longer makes the browser leave the page.
- **/start asks before it forgets your key** ('use another key' needs a second click).
- **The FAQ says what stays as in your Blender** (color management, cameras, lights, materials) and what the service sets (resolution, samples, denoising, engine, Blender version).

## 0.4.102 (2026-10-14)

Receptionist, client and Blender add-on 0.1.10.

- **Large uploads finish on slow lines.** The CLI, the Blender add-on (0.1.10) and the browser no longer give up after eight cut parts while the upload keeps moving, and they shrink the parts so each finishes in about a minute. At 2 Mbps a 5 GB upload used to stop after about 250 MB. The browser keeps showing the progress after a cut.
- **A storage error while an upload part is written is answered as retryable** (503 storage_error, the position does not move), and a full disk as 507 insufficient_storage, instead of a 500 that the sender retried eight times.
- **Saving a card that already used its free credit** now says on the return page that large files (.blend up to 5 GB) are open for this key, and how to pick the same file again on /start.

## 0.4.101 (2026-10-14)

Receptionist.

- **Estimates no longer grow from tiny test renders.** A render too small to measure (for example 160x90 at 2 samples, mostly start-up time) no longer sets the time per frame. The sample on /start was still quoted at about 33 GPU-seconds for a preview and a final past the free time; it renders in about 2.

## 0.4.100 (2026-10-14)

Receptionist and client.

- **Estimates are not inflated by our own tests.** A new scene's estimate no longer takes in the heavy jobs of our endurance tests; a scene with the same content as one measured before (the sample, for one) uses that measurement. The sample on /start showed a 1-frame preview at about 200 GPU-seconds and a final past the free time; it renders in about 2.
- **A preview counts only previews ahead of it.** Previews go before final parts, so "jobs ahead" no longer counts the final parts in the queue.
- **After a product or turntable preview, the suggested final uses the same preset** (4 product PNGs or the turntable MP4), not a 1080p orbit.

## 0.4.99 (2026-10-14)

Receptionist and client.

- **Previews stay quick while a heavy final runs.** When every other GPU worker is busy, the last free one keeps room for previews instead of taking a long part of a final.
- **Heavy long finals fit.** The parts of a long final are sized from the estimate, so a 4K scene at minutes a frame is no longer refused for one part's GPU-hours, and the preflight checks the limit per part.
- **A render whose parts were all done when the service restarted finishes within minutes** (it could wait up to 50 minutes).
- **Errors are easier for agents to act on:** 405 and unknown routes carry a code and what to do, MCP errors link to the docs, and a remote MCP call without a scene says how to upload a file from the user's computer (/upload).
- **Registering a card opens 5 GiB uploads also when that card's free bonus was used on another key** (the bonus itself stays once per card).
- **The CLI says how a large download is going** (zip n of N, how much so far, fetching again).
- **Paying one top-up page closes the key's other open top-up pages**, so a payment is not made twice by accident; the same page is reused after a restart.

## 0.4.98 (2026-10-14)

Receptionist and client.

- **After a 402, paying starts the same render; nothing to send again.** The agent gets the kept order (`resume.order_id`) and is told the render starts by itself once the payment arrives; it follows the order with `render_status`. The CLI prints `janction-render status o_...`. The Stripe success page names the job the payment started.
- **A render is never started twice after paying.** A resend is matched to the kept order by the scene's content, not its id (MCP sends a new scene id each time), so a resend before or after the payment returns the same job and is charged once.
- **The order waits 24 hours,** as long as the Stripe payment page stays open (it was 1 hour).
- **A final over 240 frames gets one 402 before it is split,** with the payment link, instead of a 402 per part that never reached the user; after paying it starts as one split job.
- **Heavy scenes get the time they need.** Each part's time limit follows the estimate (up to 30 minutes), and a single frame that still runs out of time is drawn again once with 30 minutes on keys that have bought credit. Time lost to a part that ran out of time is not charged, also when the job fails.
- **Frames finished before a part runs out of time are kept.** Only the frames that were not finished are drawn again.
- **/start answers the first questions before you pick a file:** no sign-up, the first credit with no card, no GPU or Blender needed, the formats it takes, preview in seconds, and the price after the free part.
- **Large results are easier to fetch.** A job with many files lists zip links of about 1 GiB each; the CLI fetches them in slices and fetches only a cut slice again; the Blender add-on 0.1.9 picks up the frames of a split final.

## 0.4.97 (2026-10-14)

Receptionist.

- **A heavy final no longer fails when one part runs out of time.** A part that runs past the per-part time limit is split into smaller parts and queued again, and the job goes on; the time lost is not charged. Only a single frame that still does not fit fails the job.
- **Parts are sized from the estimate.** A final is cut so that each part is expected to take well under the time limit, so heavy scenes start with smaller parts.
- **Pricing and limits from one source.** The FAQ and guides no longer say "240 frames per job".

## 0.4.96 (2026-10-14)

Receptionist.

- **Finished videos are read back where ffprobe is missing.** The check added in 0.4.95 now counts the frames and reads the codec and frame rate with ffmpeg alone. In 0.4.95 a host without ffprobe marked correct MP4 finals as failed (not charged).

## 0.4.95 (2026-10-14)

Receptionist and client.

- **Videos are checked before they are called done.** Frame count, frame rate and codec are read back from the finished file, also GIFs, and also where ffprobe is missing (ffmpeg counts the frames). A file that does not match is a failure on our side and is not charged.
- **/start shows the preflight.** After the scene is read, the page says whether it can render as a final with these settings, and what to check first (the same answer as `POST /v1/scenes/{id}/preflight` and `scene_info`).
- **Dependencies in one shape.** The preflight lists the assets that were sent, the images packed into the .blend and the files that are missing, each with what to do. The CLI says when it could not look for textures next to a .blend (install `janction-render[blend]`, or pack them).

## 0.4.94 (2026-10-14)

Receptionist, GPU worker, CLI / local MCP server and Blender add-on 0.1.8 (docs/67 §14).

- **Projects with large textures (still behind a server setting).** Files a `.blend` refers to (textures, caches) can be sent in parts into the scene, each with the same per-part checks and resume as the scene itself: up to 5 GiB each and 15 GiB or 500 files per scene for keys with a registered card or prepaid credit (no change for other keys). `POST /v1/files/{id}/manifest` takes the list you have and returns which files are still missing. The CLI and the Blender add-on 0.1.8 send large files this way by themselves.
- **GPU workers.** Large textures are fetched once per machine and kept like large scenes, so the parts of one render do not fetch them again.
- **Exact limits.** A split upload one byte over the limit is refused when it is created.
- **/start and /upload.** After a resume, the time left is measured from where the page picked up (it said a few seconds at 92%); a re-sent file that the service already had shows the name it was sent with.
- **Operators.** An alert when free space, minus what uploads in progress still need, falls under 200 GB, or when an upload was refused for space.

## 0.4.93 (2026-10-14)

Receptionist only.

- **`GET /v1/capabilities`.** What the service takes right now: frames per call and per part, free-time and prepaid resolution, input formats and sizes, outputs, engines, Blender versions, presets and retention; with a key, also that key's own limits (whether 4K is open, how long its results are kept). `render_info` carries the same limits, and a test checks that the MCP tool texts, facts.json and the OpenAPI say the same numbers.
- **`POST /v1/scenes/{id}/preflight`.** Before any GPU time: `ready`, `warning` or `blocked` for the settings you intend to render with, each check with what to do (missing files, no camera, engine, frames outside the scene, frames or resolution over the limit, the job too long, payment needed, spending cap). `strict: true` turns missing files into `blocked`. `scene_info` over MCP carries the same answer. Nothing is rendered or charged.
- **Pay, and the render starts.** A render that got 402 is kept for an hour (`resume.order_id`); when the top-up or the free card credit lands, it starts by itself with the same idempotency key, so sending it again returns that job instead of a second render. Follow it with `GET /v1/jobs/{order_id}` or `render_status`.
- **Revoked keys.** Signed download links stop working once the key that made them is revoked.

## 0.4.92 (2026-10-14)

Receptionist and Blender add-on 0.1.8.

- **Blender add-on 0.1.8: long and 4K renders.** The add-on no longer cuts a render to 240 frames and 1920x1080. It sends up to 3,000 frames (the service renders them as parts of 240 and joins one video) and up to 3840x2160; the service decides 4K by the key (prepaid credit). The files of a long render can be fetched with the key by the names the job lists.
- **Before you press.** Estimates and `GET /v1/me` say how long results are kept (24 hours after last use, 7 days for keys that have topped up) and how long download links last. A final on a scene whose image files were found missing says so when it is accepted (`missing_assets`), with how to cancel and fix.
- **Errors.** Every error carries `message` (same as `detail`), and the front door's 413 and 400 now have the same shape as the rest (`code`, `retryable`, `recommended_action`, `request_id`). A failed render says what was charged (`failure.charged_yen`). A failure nobody has classified is treated as ours: not charged, no free time used.
- **No double orders from the browser.** /start sends an idempotency key with the render, so a double click or a page that comes back does not render twice.
- **Housekeeping.** Access logs no longer carry signed link tokens; two requests reading a long render at the same moment no longer join the video twice; the daily ledger check flags any charge for a failure on our side; tool descriptions read their limits from the same settings as the service.

## 0.4.91 (2026-10-14)

Receptionist, GPU worker, CLI / local MCP server and Blender add-on 0.1.7 (docs/67 §12-13).

- **Over the limit, say how to send more.** A 413 for a `.blend` over a key's cap carries `upgrade` (5 GiB with a registered card, which is free; a signed link the user can open) and `recommended_action: ASK_USER`; `/start` shows a button for it. Keys without a card stay at 1 GiB per file (decision of 2026-10-14).
- **Resumable uploads (still behind a server setting).** `Upload-Checksum: sha256 <base64>` per part (tus checksum; a damaged part gets 460 and is sent again from the same offset), used by the browser, the CLI and the add-on; `GET /v1/uploads/limits` adds `today_left_bytes`, `retention_hours` and `upload_charge`; `/start` shows the time left; a key that sends the same content again gets its earlier scene back instead of a second copy; 507 carries `Retry-After`; the writer lease is 90 s and renewed while a part streams; expired uploads are counted in events.
- **GPU worker.** A chunk taken back after a worker restart clears its work dir on the same machine (a cached large scene failed with SameFileError there); a large input is fetched once per machine; the load allowance is 15 s per GB above 256 MB (measured: the first frame starts 4 s after the container for 5 GB).

## 0.4.90 (2026-10-14)

Receptionist only.

- **A canceled render counts only what finished.** Seconds a worker reports for a part it was stopping after a cancel no longer count against the free time or the credit.
- **Body size without a declared length.** Requests that stream their body without a length are held to the same size limit as any other.
- **Asset size.** An asset over the size limit is refused with what to do: lower the texture resolution, compress it, or pack it into the .blend.
- **Resumable uploads (groundwork, still closed).** The writer lease on an upload is short and renewed while a part streams, so a receptionist restart does not hold an upload for half an hour.

## 0.4.89 (2026-10-13)

Receptionist and client.

- **Did the user get the result?** The scorecard and the daily report count finals whose files were actually fetched (per job, a split final counted once) and keys that went from a first action to a received result, and list by client the finals that were never fetched. A finished job is not the same as a delivered result.
- **The same link twice.** A key that sends the same `scene_url` again within an hour gets the scene it already sent instead of a second download (a call cut off at the edge used to fetch the whole file again).
- **Clearer refusals.** An /upload link given as an asset says to pass it as `scene_url`; the CLI no longer suggests `asset_urls` for an asset over 128 MB, which a link cannot carry either; a job that waited in the queue until the retention window ended says so instead of a bare not-found.

## 0.4.88 (2026-10-13)

Receptionist and client.

- **Long finals from the terminal.** `janction-render render ... --frames 1-1440 --output mp4 --wait` gets the joined video: a long final's whole video carries a download URL, the archive endpoint takes the long final's job id, and `only='mp4'` picks the one joined video instead of every part's.
- **Frames of a long final are frames.** Part frames (`part-01_frame_0001.png`, ...) count as frames for `only='frames'`, the MCP reply (the first three are listed, not hundreds) and the progress page.

## 0.4.87 (2026-10-13)

Receptionist only.

- **Large-scene test (docs/67 P2).** While a server setting, the keys in a server setting get the card / prepaid tier (`.blend` up to a server setting, 5 GiB) and a daily total of a server setting (50 GiB), so the 1 / 3 / 5 GB scenes and their retries can be sent with the operator key. Other keys and the limits for users do not change; a server setting or `off` ends it.

## 0.4.86 (2026-10-13)

Receptionist; no worker change.

- **3,000 frames per instruction.** One final can now be up to 3,000 frames (about two minutes at 24 fps; a one-minute animation is 1,440 frames), still rendered as parts of 240 under one job id and joined into one video. The whole job's price is held before it starts, so a final that the credit does not cover does not begin. a server setting sets it.
- **Resent render_final with a script or link.** The automatic idempotency key of the MCP `render_final` is made from the arguments the agent sent, so a resend with the same `scene_script` or `scene_url` returns the first job too (0.4.85 keyed it on the uploaded scene, which is new on every call, and rendered twice).

## 0.4.85 (2026-10-13)

Receptionist; no worker change.

- **Finals over 240 frames from Claude.ai and ChatGPT.** The remote MCP `render_final` now runs long finals as parts under one job id, like `POST /v1/jobs` (it refused anything over 240 frames). When every part is done, the parts' videos are joined into one file (`output`), and the progress page works for the whole job.
- **Limits stated as they are.** Tool descriptions, `/facts.json` (`final_render_limits`) and estimates say up to 1,000 frames per call, 1920x1080 on free time and 3840x2160 with prepaid credit. A key that has topped up gets 4K even while its free time covers the job.
- **Retention stated as it is.** Files are kept 24 hours after last use, 7 days for keys that have topped up; download links last 24 hours and asking again gives fresh ones while the files are kept.
- **Not charged for our retries.** When an attempt fails and is retried (a busy shared GPU, a version switch) and the job then succeeds, only the successful attempt is charged. A worker that could not hand back its result, or a busy shared GPU, counts as our failure.
- **No double renders on resend.** The MCP `render_final` (remote and local) makes an idempotency key from its arguments when none is given, so the same call repeated within two minutes (an agent retrying after a timeout) returns the first job. Pass a new `idempotency_key` to render twice on purpose. The HTTP API is unchanged.
- **Split finals report honestly.** A failed part no longer marks the whole job failed while other parts are still rendering; parts not yet queued resume after a restart.
- **Stuck finishing.** A job whose frames were all rendered but whose video assembly was interrupted by a restart is finished by the sweeper.
- **Larger scripts over MCP.** The remote MCP endpoint takes requests up to 3 MB, so a `scene_script` up to the 2 MB script limit goes through; anything larger gets a JSON-RPC error that points to /upload.
- **/upload scripts.** A script someone put on /upload that is not a render script is refused with the reason; it no longer counts against the AI app's key.

## 0.4.84 (2026-10-13)

Receptionist, GPU worker, CLI / local MCP server and Blender add-on 0.1.6 (docs/67). The new paths for large scenes are behind switches that are off by default.

- **Resumable uploads (off until a server setting).** `POST /v1/uploads` takes a file in parts (tus 1.0: `HEAD` for the offset, `PATCH` parts of up to 96 MB, under Cloudflare's 100 MB per request) and resumes after a dropped connection, a closed browser tab or a receptionist swap; the same file picked again (same name, size and sha256 or browser timestamp) continues where it stopped. `.blend` files up to 5 GiB for keys with a registered card or prepaid credit, 1 GiB otherwise; one upload at a time per key; daily totals stay 5 GB for keys without a card, 10 GiB with one, 1 GiB per network without a key. a server setting opens it only to the keys in a server setting. While it is off, `/upload` and `/start` stay as they were and the clients fall back to single uploads.
- **Clients.** The CLI, the local MCP server and the Blender add-on 0.1.6 send scenes over 64 MiB in parts when the service offers it, and continue an interrupted upload when run again.
- **GPU worker (off until set).** a server setting keeps a scene of 256 MB or more on the machine between frame chunks; a server setting shows it to the render container read-only instead of copying it in; a server setting makes a worker skip larger scenes. Always on: the scene goes into the container from a file instead of memory, chunk timeouts add a server setting seconds per GB above 256 MB, and the worker reports the copy and load seconds.
- **Fixes.** The `.blend` check reads the first bytes instead of the whole file (the receptionist has 2 GB of memory); a `/upload` link adopted by a key is hard-linked instead of copied; multipart temp files go to the data disk instead of the 256 MB in-memory `/tmp`; the 1 MB body cap applies again to the JSON routes under `/v1/files`; a local path as `scene_url` points to `/upload`; a batch retry that lands while the batch is finishing is no longer lost.
- **MCP.** The instructions tell the agent to send the user to `/upload` for a local file. `upload_link` / `upload_status` stay hidden until a server setting.

## 0.4.83 (2026-10-13)

Local MCP server (stdio) tool descriptions; receptionist unchanged apart from the version.

- **Destructive tools say what they do.** `render_cancel`: queued frames are dropped, rendered frames are charged and stay downloadable, the rest of the held GPU time comes back, it cannot be resumed, only the starting key may cancel, a job being assembled cannot be stopped. `render_unshare`: the page URL stops working, its copy, script and shown request are deleted, it cannot be undone (sharing again gives a new URL), the job's own files are untouched. `render_share` and `render_info` (read-only, no charge, rate-limited with `retry_after_s`) likewise. `job_id` mentions split finals (`b_...`). Prompted by Glama's automatic tool grades (render_cancel C, render_unshare B, inspected 2026-10-02).
- The remote MCP keeps its reviewed descriptions until the directory reviews finish (a server setting switches them).

## 0.4.82 (2026-10-13)

Receptionist; no worker change.

- **/upload takes files over 1 MB.** `POST /v1/drops` was still under the 1 MB body cap meant for JSON requests, so every file over 1 MB got HTTP 413 although the page states 100 MB. The route keeps its own cap (a server setting, and Cloudflare's 100 MB in front).

## 0.4.81 (2026-10-13)

Receptionist; no worker change.

- **Switchable Product Video entry.** a server setting (default `/`) points the result-screen button and the `/v1/outcomes` note at the Video service's browser order page (`/start`) once that is deployed, without a release here.
- **CI.** The paid-retention test pins the disk guard (the runner has tens of GB free; the 500 GB fallback is by design). The loop-guard meta-test is marked xfail on Linux while the detector difference (anyio 4.15 / starlette 1.8 on the runner) is investigated (docs/66 §7).

## 0.4.80 (2026-10-13)

Receptionist; no worker change.

- **Three problems, three guides.** The top page and /pricing link /free-blender-cloud-rendering, /render-blender-without-gpu and /blender-cloud-rendering right under the first buttons (docs/64 §11: these pages were only reachable from the list of 25 guides, and Google had crawled but not indexed most of them).
- **/start re-checks after Stripe.** When the payment panel is open and the tab comes back, the balance and the quote are fetched again (docs/62 P1-1).
- **Listing pack tools.** `product_video_listing_pack` / `_submit` / `_status` relay the Video service's store listing pack; gated with the other Product Video tools (a server setting).
- **Staging gate.** `tools/stage_zip.py` builds the deploy zip only from a clean, pushed HEAD whose CI run succeeded (`--allow-red --reason` for a recorded exception) and copies it to the GPU box.

## 0.4.79 (2026-10-13)

Receptionist; no worker change.

- **Condition in the same sentence.** The first "up to 500 JPY" / 「最大 500 円分」 on every page carries the card condition inside that sentence (AI answers quote excerpts, not whole pages).
- **One rule for Render vs Product Video.** /products, llms.txt, facts.json and the `/v1/outcomes` replies say the same thing: raw renders you finish yourself (your own .blend or bpy scene, transparent stills, a plain turntable MP4, EXR, many frames) are JANCTION Render at GPU cost; a finished piece you publish as is (captions, ending, backdrop colour, looping 360, four shop images with a listing, revisions without re-rendering, projects, batches, the listing pack) is Product Video at GPU cost plus a production fee. The Video side shows the same rule (docs/65).
- **CI.** `tools/incident.py` referenced an undefined `_data_dir`, which failed the fatal ruff check on every push since 0.4.62; fixed.

## 0.4.78 (2026-10-13)

Receptionist pages; no worker change.

- **Product Video line from the live catalogue.** The one-line description on /products, /pricing, llms.txt and facts.json now groups the public Video catalogue by kind (product video, 360-degree video, four product images, store listing pack) with the production fee and the typical total for each length, so the page follows the catalogue when prices change.

## 0.4.77 (2026-10-13)

Receptionist pages; no worker change.

- **The card condition on every page that names the maximum.** Pages that say "a welcome credit of up to 500 JPY" now carry the condition at least once on the same page (100 JPY with no card, 400 JPY more after registering a card, which is not charged). /products, /compare and their Japanese versions showed only the maximum. `pages.welcome_terms` adds the clause when a page lacks it, and a paid-mode test over every public page keeps it that way (docs/66).

## 0.4.76 (2026-10-13)

Receptionist; no worker change. Everything here is hidden until the Product Video service opens (a server setting, a server setting).

- **Product Video as a feature of JANCTION Render.** One line on /products, /pricing, llms.txt and facts.json (prices read from the Video catalogue: GPU at 0.1 JPY per GPU-second plus a production fee; a plain turntable or stills stay cheaper through /v1/outcomes). A "Make a product video from this 3D" link on /start and in `GET /v1/jobs/{id}` (`product_video`) when the input is a 3D file or the job is a turntable or product shots. Four relay tools for the remote MCP (`product_video_quote` / `_submit` / `_status` / `_revise`) that hand the caller's key or token to the Video service unchanged and send the stored 3D file across so the user does not upload it twice. The morning report counts Product Video captures as revenue (docs/65).

## 0.4.75 (2026-10-13)

Receptionist (/start and the preview critic); no worker change.

- **First-time run-through fixes.** Walking through /start as a new user with their own .blend (docs/64 §7): the wait line said "about about 5 seconds"; a key kept in the browser that the server no longer knew produced "unknown or revoked key… POST /v1/keys" (now the page drops it and makes a fresh key); the preview's notes listed "cut by the frame edge" twice (the critic now says each sentence once).

## 0.4.74 (2026-10-13)

Receptionist pages and the morning report; no worker change.

- **Browser first in the free page's answer.** The opening of /free-blender-cloud-rendering (EN/JA) no longer says an MCP client or the CLI is needed: nothing to install, open /start, try the sample or your own file; MCP and the CLI are the other ways in (docs/64 FREE-01).
- **Japanese wording.** "使えますです" in the sentence about a second key on the same network is fixed (a replacement rule kept the sentence's own です).
- **Measurement for free users.** The morning report shows keys that rendered their own input (not the sample), keys that only saw the sample, and keys that got only the network's remaining welcome credit (shared Wi-Fi); `tools/gsc_import.py` groups a Search Console CSV export by search intent (free / no_gpu / cloud / upload / slow / free_farm / brand / agent) and names the receiving page (docs/64 FREE-02, FREE-04, FREE-08).

## 0.4.73 (2026-10-13)

Receptionist pages only; no worker change.

- **The free page starts in the browser.** "How do I start for free?" now begins with /start ("Try the sample first": no file, no payment), then your own file; connecting an AI client through MCP and the terminal come after. Until now step 1 was the MCP connection (docs/63 UX-02).
- **One way of saying the frame limit.** Every page says: up to 1,000 frames per instruction, rendered as parts of 240 under one job id, 1080p on free time and 4K on prepaid credit. About thirty places (comparison tables, FAQs, facts, llms.txt) still said "240 frames and 1080p per job"; a test now scans the public pages for the old wording (docs/63 DATA-01).

## 0.4.72 (2026-10-13)

GPU workers.

- **Scripts can write next to themselves.** A job's working folder (where the scene file is placed and Blender starts) is now writable by the render process, so a script written for a local Blender that creates an output folder or writes a file there no longer fails with a permission error. The scene file and assets you sent stay as they are, and the service still sets the output path, resolution and samples.

## 0.4.71 (2026-10-13)

Receptionist and the daily reports; no worker change.

- **The card option reaches agents.** When a key's free GPU time is used up and saving a card (no payment) would add free time, `402 payment_required` on both MCP servers now carries `card_offer` (with a `link` the user can open) and `tell_user` names the card option before the top-up; `how` and `next` do the same. Until now only the REST reply carried `card_offer`, so agents on Claude.ai, ChatGPT and the CLI offered only the paid top-up (docs/62).
- **Card first on the amount chooser.** The page a 500 JPY top-up link opens (`/b/…`) shows "Register a card" first for eligible keys; `card_offer.link` opens a one-button page that leads to Stripe's card-saving page.
- **Measurement.** `card_offer_shown` (once per key per 6 h), `topup_page_opened` / `topup_page_chosen`, and `via` on `checkout_created` (402 / api / chooser). The daily summary splits checkout pages into "opened by a person", "attached to a 402" and "0 JPY card registration"; the morning welcome line adds keys that got a 402, saw the offer and opened the card page; `tools/journey.py` follows the card path per key.

## 0.4.70 (2026-10-13)

Receptionist and the daily IndexNow job; no worker change.

- **Update dates follow the wording.** The footer date, the sitemap `lastmod` and the structured data's `dateModified` are never older than the last change to the price and free-credit wording (`billing.public_terms_date`: the pricing version or the day the card-based welcome credit started, whichever is newer). 103 of 153 sitemap URLs had kept 2026-10-08 although their wording changed on 2026-10-12. `/changelog` now carries the date of the newest release. The pricing version recorded on jobs and in the ledger is unchanged.
- **IndexNow for every changed page.** `tools/indexnow_daily.py` remembers the `lastmod` it last sent for each URL (`data/indexnow_sent.json`) and sends every URL whose `lastmod` changed, instead of only URLs dated today. The first run sends every URL once.
- **Older descriptions.** /facts, facts.json (`pricing.superseded`) and llms.txt (English and Japanese) say that the free beta, 10 free GPU-minutes per key per day from 2026-09-30 to 2026-10-08, has ended, and that articles, directory listings and search snippets from that period are out of date.

## 0.4.69 (2026-10-13)

GPU workers (deployed first, at 13:30 JST) and the receptionist.

- **Compare and multi-camera previews render again.** From 0.4.63 (2026-10-12 17:50 JST) a line added to the preview's Blender expression lost its quotes in the shell and raised `NameError: name 'script' is not defined`. The rest of the expression did not run: previews with `environment='compare'` and with `cameras=[...]` failed with "compare rendered 0 of 4 presets", and other previews carried the NameError as a warning and came back with a verdict that had not checked the scene. A new test splits the generated command the way bash does and checks the expression for every input kind.
- **What the service is, on the status and changelog pages.** One paragraph near the top of /status and /changelog (English and Japanese): the one-line definition, the MCP URL, /start to try it in a browser, the free credit and the price, from the same source as the pricing page.

## 0.4.68 (2026-10-13)

Receptionist only; no worker change.

- **Scripts that write their own output.** A script written for a local Blender often creates an output folder next to itself or sets `scene.render.filepath`; in the render container that fails with a permission error before the scene is built. The failure's reason and `recommended_action` now say so and name the lines to remove (`os.makedirs`, `scene.render.filepath`, `bpy.ops.render.render`; use `tempfile.mkdtemp()` for a real scratch file). Shown on /start, in the MCP tools and in `GET /v1/jobs/{id}`.

## 0.4.67 (2026-10-13)

The structural refactoring in one pass (docs/60 §14: ARCH-02, ARCH-03, SEC-04/05). Receptionist only; no worker change; no change to any URL, response or price.

- **app.py split.** The 6,500-line receptionist is now shared layers (`core`, `views`, `intake`, `checkout`, `submit`, `sweep`) and route modules (`routes_public`, `routes_keys`, `routes_files`, `routes_shares`, `routes_batches`, `routes_partner`, `routes_jobs`, `routes_start`, `routes_worker`, `routes_billing`). `app.py` keeps the app, middleware, error handlers and the MCP mount, and forwards `appmod.X` reads and writes to the part that owns the name, so tests and tools did not change.
- **Typed request bodies.** `server/schemas.py` holds pydantic models for the POST bodies; `openapi.json` is generated from them (the hand-written dicts are gone). Runtime parsing is unchanged (its error wording is the agent contract).
- **OAuth scopes.** `render` (everything; the default and what every existing token and API key has), `read` (status, links, estimates, quota and billing only) and `share` (publish or remove share pages). A read-only connection gets `insufficient_scope` with a reconnect hint instead of rendering; the consent page says what the app will be able to do.

## 0.4.66 (2026-10-12)

Phase 2 and 3 leftovers (docs/60 §13). Receptionist and the stdio package; no worker change.

- **MCP sharing, third stage.** The `billing` reply is built once (`mcp_common.billing_reply`) for the remote and the stdio server. What remains different between the two servers is transport (the stdio server saves files and uploads local paths; the remote server returns links and images), not wording.
- **/start: save all frames as a ZIP** (one request with the key; the browser saves `<job_id>.zip`).
- The distribution channel ledger skips the operator's own check tags (`smoke-…`).

## 0.4.65 (2026-10-12)

Phase 3 of the refactoring requirements, first part (docs/60 §12): one source for the numbers in every public text. Receptionist only.

- **A page for "fix Blender render errors"** (/fix-blender-render-errors, en and ja): pink textures, script exceptions, a script that built nothing, no camera, no light, out of GPU memory, timeouts, import failures and our-side failures, each with the code the API and the MCP tools return and the fix.
- **Distribution channel ledger.** `docs/channels.json` records every listing and package (state, last update) and `tools/channel_ledger.py` adds the inflow per channel tag from the ledger (keys, first success, finals, paying keys and yen).
- **Prices, limits and retention in every public text follow the settings.** The metered price, the free preview minutes, the retention hours, the frames per job part, the minimum top-up and the welcome credit are written once (`server/terms.py`, from the billing settings) and every page, FAQ, guide, Markdown variant, llms.txt and pricing JSON is rendered through it. A new test renders every public page with unusual values (0.37 JPY, 3 minutes, 37 hours, 333 frames, 700 JPY) under both welcome models and fails if a default number is still written by hand.

## 0.4.64 (2026-10-12)

Phase 2 of the refactoring requirements, third batch (docs/60 §11). Receptionist and the stdio package; no worker change.

- **MCP sharing, second stage.** The estimate body, the estimate's next-step text and the scene_info reply are built once in `janction_render/mcp_common.py` for both the remote and the stdio server; the estimate's "too big" text states the current limits (parts of 240 frames under one job id, 1080p on free time, 4K on prepaid credit).
- **/start: plain backdrop.** A checkbox on the preview's next steps hides the HDRI (`environment_visible=false`) for the next preview and the high-quality still.

## 0.4.63 (2026-10-12)

Phase 2 of the refactoring requirements, second batch (docs/60 §10). Additive only; the receptionist and the workers both change (workers clean up leftover work dirs at start).

- **Erase my data now.** `DELETE /v1/me/data` deletes every scene, render and share page of the key immediately (running jobs are cancelled first); the billing ledger and the key stay. Recorded as `data_erased`.
- **A render being assembled cannot be cancelled** (`finalizing`): cancelling during video assembly used to leave a cancelled job with an output file. The cancel call returns the job with a note instead.
- **Browser funnel in the scorecard.** /start events are grouped by the per-browser tag into landing → input → read → quote → render → success → download → next, with the drop at each step (visit without input, input failed, quote without render, render without success).
- **/start** shows the key's spending caps and that failures on our side are not charged, says the remaining time in Japanese on /ja/start, and has `aria-live` progress, `role=alert` errors and labels on its inputs.
- **Restore drill.** `tools/restore_drill.py` unpacks the latest nightly backup into a temp dir and checks integrity, the ledger invariants, the audit chain and the backup age (RPO), without touching production; backups now keep the audit `ANCHOR`.
- Workers remove work directories left behind by a crashed process (older than a day) when they start.
- **One source for the MCP servers' shared pieces.** The preset rules, the job-parameter builder and the argument docs that the remote and the stdio server used to keep as separate copies live in `janction_render/mcp_common.py`; the receptionist's preset names come from the same place.
- **User classes and cohort retention in the scorecard.** External keys are counted as unclassified / tried / confirmed real / paying / recurring paying, and D30 and D90 retention are reported per cohort.
- **OpenAPI request bodies.** `POST /v1/jobs`, `/v1/estimate`, `/v1/files/url`, `/v1/keys`, `/v1/try`, `/v1/me/limits`, `/v1/billing/checkout` and `/v1/jobs/{id}/share` describe their JSON bodies (fields, enums, required).

## 0.4.62 (2026-10-12)

The rest of Phase 1 of the refactoring requirements (docs/60 §8, docs/61). Additive only.

- **Signed webhooks.** Every `notify_url` POST carries `X-JR-Timestamp` and `X-JR-Signature: v1=hex(HMAC-SHA256(secret, "<timestamp>.<body>"))`; the per-key secret is in `GET /v1/me` (`webhook.secret`). Receivers can reject forged or replayed calls.
- **Workers read only their own inputs.** A worker that names itself (`X-Worker-Id`) can fetch the scene and assets only for chunks assigned to it.
- **A script that builds nothing is reported.** When a bpy script leaves Blender's startup scene untouched (default cube, light and camera), the preview critic says so (`default_scene`, check) instead of scoring the cube.
- **Intake can be paused without stopping the service.** `tools/incident.py pause-intake "<reason>"` writes `data/INTAKE_PAUSED`; new renders get 503 `intake_paused` (`WORKERS_UNAVAILABLE`, retryable) while status, downloads and billing keep working; `/v1/health` shows `intake` and the reason in `notice`; `resume-intake` lifts it.
- **Stripe subscription events in any order.** An older `customer.subscription.*` event no longer overwrites a newer state (the last applied event's `created` is kept).
- **GPU out-of-memory is classified** from Blender's "out of GPU memory" wording too (`OUT_OF_MEMORY` / `JOB_TOO_LARGE`), so the agent gets the "reduce resolution or geometry" advice instead of a generic failure.
- **The job journal no longer stores client IPs** (the database keeps them for 90 days, as published). The OAuth refresh error says that the access token expires after 30 days and that the OAuth flow should be run again. `mcp_rpc` events carry `request_id`.
- **Docs and tooling.** `docs/env_vars.md` is a generated inventory of every `JR_*` setting (`tools/env_inventory.py`, checked by a test); `docs/61` states the internal SLO targets, the list of endpoints that need no key, and the per-client compatibility table. The `server` extra now requires `mcp>=2.0` (the remote server needs it).
- **/start and the result page.** /start shows the expected wait (queue) before you press render, has a "Preview again" button, sends `X-Client: web/start` (its renders are no longer counted as plain API use), tags its browser events with a per-browser id and records `render_started`, and lays out on phones. The signed progress page (`/w/…`) now ends with next steps (what to ask the agent for, a feedback link, /start) and the expiry time instead of only a download. Download events distinguish an inline view from a save.

## 0.4.61 (2026-10-12)

- Every page shows one update date: the footer, the sitemap `lastmod` and the structured data's `dateModified` come from the same place.
- Meta descriptions on the terms, privacy, legal notice, security and support pages; the benchmarks page is dated by its latest measurement (2026-10-12); the footer names the Blender versions the workers run; images declare their height; the viewport sets `initial-scale=1`; the guide list links the product-shots and render-farm comparison guides.
- /status is indexable and in the sitemap, and defines the 7-day success rate (finished previews and finals, done and failed; cancelled jobs not counted; failures caused by the user's own script included).

## 0.4.60 (2026-10-12)

P0 of the refactoring requirements (docs/60): correctness of results, money, agent safety and operations. No API or MCP contract changes; every field is additive.

- **Broken output is not a success.** Every frame a worker sends is checked (PNG signature, header and end marker; EXR signature); an empty or truncated frame fails the job as `OUTPUT_VERIFICATION_FAILED` on JANCTION's side (nothing charged). A video is probed after encoding (`ffprobe`), and a file with fewer frames than were rendered is a failure, not a download. The preview critic no longer scores an unreadable preview 100.
- **JANCTION-side failures cost nothing.** A job that fails for a reason on our side (worker lost, container, encoder, sandbox, verification) is settled at 0 JPY even when some chunks had finished, as the terms say. Free time is not consumed by them either.
- **Stripe events are applied once and in any order.** Each webhook event id is recorded; a refund that arrives before its payment's credit is held and applied the moment the credit lands; chargebacks (`charge.dispute.*`) take the disputed amount back (and restore it when the dispute is won); failed or expired Checkout sessions are closed.
- **Jobs and ledger rows carry the pricing version and the rate they were quoted with**; a job is settled at the rate in force when it was submitted.
- **Holds cannot get stuck.** Lost chunks are requeued by the sweeper as well as by worker polls, so a job whose workers all went away is failed and its reservation released even with no worker polling; `ledger_check` flags a job that has held credit for over a day.
- **Worker binding.** A worker names itself (`X-Worker-Id`) and the receptionist accepts a chunk's frames, completion or failure only from the worker it was assigned to.
- **Cancelling a split final** (`b_…`) stops the parts not yet submitted and reports the job as `canceled`, not `failed`.
- **`request_id` everywhere.** Every response carries `X-Request-Id` (yours is echoed if you send one); REST and MCP error bodies and the `api_error` / `mcp_tool_error` events carry the same id. Unhandled errors return the common JSON error shape (`internal_error`, `INTERNAL_ERROR`) instead of a bare 500 and are recorded.
- **Remote MCP errors for bad arguments are `INVALID_INPUT` / `FIX_INPUT`, not retryable internal errors.** `render_final` takes `max_yen` and `idempotency_key` on the remote server too. Job views mark `log_tail` and `warnings` as untrusted output (`untrusted`, `untrusted_note`).
- **Limits are stated the same way everywhere:** up to 1,000 frames per instruction (run as parts of 240 under one job id), 1920x1080 on free time and 3840x2160 on prepaid credit (tool docs, prompts, skill, guides, npm README).
- **Retention as published.** Client IPs are cleared from the database after 90 days (a server setting); Blender's console tail is deleted with the job; an unshared page drops its script and prompt; share media is cached for 1 hour instead of 24; the privacy page describes what the logs keep.
- **Security.** `scene_url` / `asset_urls` refuse credentials in the URL; asset downloads stream to disk instead of buffering in memory; glTF null-fixing skips files over a server setting and survives deeply nested JSON; `.usdz` archives are checked for entry count and compression ratio; webhook (`notify_url`) log lines carry no query or credentials; a server setting makes the worker fail a job instead of falling back from an extra isolation layer to runc.
- **Operations.** `/v1/health` reports `degraded` and `workers_online`; the watch alerts on receptionist 5xx and on payment failures; the audit chain verifies after old days are pruned (anchor); `server.sh build` keeps the previous image as `:prev` and `server.sh rollback` swaps back to it; pytest and ruff run in CI on every push.

## 0.4.59 (2026-10-12)

- The listings say what the service is for: the MCP Registry entry, the PyPI description, the Claude Code / Codex plugin and the Gemini extension lead with the inputs (Blender scenes and GLB, FBX, USD, OBJ, STL models) and the outcomes (product shots, 360-degree turntables, animations, stills) instead of the format list.

## 0.4.58 (2026-10-12)

- The HTTP API guide has a complete app example (https://render.janction.jp/blender-render-api#embed): a user uploads a GLB, the app orders fixed-price product shots with an `Idempotency-Key` and a `notify_url`, and the webhook handler reads the job back with the key and stores the images.
- The sitemap's `lastmod` for /pricing, /products, /compare and /facts follows the update date those pages show, so a change there reaches IndexNow the same day.

## 0.4.57 (2026-10-12)

- The preview reply leads with the image: show_user is one ready line with the image (and its link for when the image does not show), next_actions lists what to do next with its time and price (the final render with the exact arguments, a 360-degree turntable video, or changing the look; a fix found by the preview check comes first), and keep says how to keep the result before the link expires. The in-chat card shows the same choices with their time and price, and a Save button.
- A scene_id unknown to the current connection no longer stops the call when scene_script or scene_url comes with it: the scene is sent again. On its own, the error says why (a scene belongs to the key that sent it, reconnecting the app makes a new key, and scenes expire 24 hours after the last use) and what to send instead.
- The Maya, Houdini and Cinema 4D sender (jr_submit.py 0.1.2) sends scene files whose names have spaces or non-Latin letters, tidied the same way the service does, instead of refusing them.

## 0.4.56 (2026-10-12)

- Codex: the Codex guide (/codex-blender#run-without-prompts), llms.txt, `janction-render connect codex` and the skill's troubleshooting explain that Codex asks before each MCP tool call and that `codex exec` cannot ask, so an unapproved call stops with "MCP tool call requires approval" and never reaches the service. They give the `~/.codex/config.toml` block that approves the read, preview, estimate and download tools one by one under the server's `url`, while `render_final` keeps asking. (A block with only the tool lines makes Codex reject the whole config with "invalid transport".)
- The skill's troubleshooting states the current job limits (1,000 frames per instruction in parts of 240, 4K on prepaid credit, 10 GPU-hours per job).

## 0.4.55 (2026-10-12)

- Blender add-on 0.1.5 (/extensions/index.json): a .blend over 100 MB is stopped before sending with what to do (unpack packed textures so they are sent separately, or make the scene lighter), and textures go in parts of up to 100 MB; one texture over 100 MB is stopped with a hint to save it smaller.
- The Maya, Houdini and Cinema 4D sender (jr_submit.py 0.1.1) checks the same 100 MB limit before sending and sends textures in parts.

## 0.4.54 (2026-10-12)

- The CLI and the stdio MCP check the size before uploading to render.janction.jp: a scene file over 100 MB is refused with too_large and a hint to pass a public https link as scene_url, and assets go in parts of up to 100 MB (an asset over 100 MB gets the same hint for asset_urls). JANCTION_RENDER_MAX_UPLOAD_MB changes the limit; a self-hosted server has none.
- The hint on a job over a per-job limit (beta_limit) no longer says beta or 1080p: detail names the limit, and resolutions above 1920x1080 need prepaid credit.
- The BlendSwap comparison page gives the upload limit as 100 MB per upload and 512 MB from a link.

## 0.4.53 (2026-10-12)

- The machine-readable pricing matches the pricing page. In GET /v1/pricing the free plan and the product prices state the current welcome credit (100 JPY of free GPU time with no card, 400 JPY more after saving a card that is not charged) and the current limits (1,000 frames per instruction, 4K on prepaid credit, 10 GPU-hours per job), also in a new `limits` block; the indicative USD price per GPU-second no longer rounds to 0. The Japanese llms.txt no longer calls the metered price planned, and the products page no longer mentions planned monthly plans.
- /pricing and /facts open with how to connect: the MCP URL, one line each for Claude.ai, ChatGPT, Claude Code, Codex, Cursor / VS Code and the HTTP API, and how much is free to start. The same is in `connect` in GET /v1/pricing and /facts.json.
- /status and /status.json (`uptime`) show measured uptime, checked from outside every 5 minutes over 7 and 30 days, and the hourly end-to-end preview through the MCP. These are measurements, not a guarantee.
- When the welcome credit expires within 3 days, the reply to a final says so (`credit_note`) even if plenty is left, so the user hears it before it lapses.
- Tighter limits on creating many keys in a short time.

## 0.4.52 (2026-10-12)

- A final whose scene sets a frame step (frame_step 2, for example) renders every frame of the requested range. Before, Blender skipped every other frame and the job failed waiting for the missing ones.
- Scene files whose names have spaces, brackets or non-Latin letters are accepted: the name is tidied and the extension kept, instead of a 400 bad_name.
- The upload size shown on /start, /upload and facts.json is the real limit for files sent to render.janction.jp (100 MB). /start checks the size before sending and suggests a download link for a bigger file.
- asset_search and GET /v1/assets/search accept more words for kind: 'hdr', 'environment' and 'sky' find HDRIs, 'material' and 'pbr' find textures, 'mesh' and '3d' find models. 'all' or any other word searches all three kinds instead of returning 400, and each result says its type (model, texture or hdri).
- Asking for the same top-up again within an hour returns the same open checkout page instead of a new one.
- Creating keys faster than the hourly limit returns a 429 that says to keep and reuse the key you already have (recommended_action REUSE_KEY; GET /v1/me checks a key). GET /v1/keys explains the same instead of only naming the allowed method.
- Codex: the GET that Codex sends on each connection gets 405 (this server has no stream) instead of 401, so Codex no longer re-reads the OAuth metadata every time it connects.
- Short and Markdown paths open the right page: /codex, /claude, /cursor and the other client names open their guide, /index.md and /llms.md open llms.txt, /ja/llms-full.txt opens the full English llms-full.txt, and '<page>.md' opens that page.

## 0.4.51 (2026-10-12)

- A bpy script that does not run no longer comes back as a success. The server refuses a script that does not parse with 400 script_syntax_error (the line number, the offending line, nothing_rendered, no GPU time used), and the GPU worker exits Blender the moment the script raises (--python-exit-code around the user's script), so the job fails with SCRIPT_SYNTAX_ERROR or SCRIPT_ERROR, the line and nothing_rendered instead of rendering Blender's default cube and scoring it 100. Found by a real-user test on 2026-10-12.
- Purpose presets on render_preview, render_final, render_estimate and POST /v1/jobs: preset='product' (4 studio shots at 0/90/180/270 degrees on a plain backdrop; the final gives 4 PNGs at 1440x1440), 'turntable' (one full turn as a 720p MP4 on a plain backdrop) and 'animation' (the scene's own camera, lights and frame range; the scene is read first when the range is not known). What you pass still wins. asset_search describes the one-call product-shot recipe for users who have no model.
- The preview critic names placeholders: a scene with no light and no world gets a sun and a grey world added automatically, and the critic now says so (auto_light, check) with the fix; an automatic camera is reported as info. Pale, low-contrast images (white on white) get washed_out; under preset='product' a busy background or a product filling under 6% of the frame is flagged; under preset='animation' a scene with nothing animated is flagged. A whitish image that blends into the background no longer scores 100.
- Pricing wording unified under the card model: the MCP instructions and tool descriptions, the FAQ, the guides, the benchmarks page, llms.txt, the README and the package descriptions say the same thing as the pricing page (100 JPY of free GPU time with no card, 400 JPY more after saving a card that is not charged, then 0.1 JPY per GPU-second). The FAQ answers are built from the server settings instead of hand-written numbers.
- /start has a "Try the sample first" button (also /start?sample=1): one click renders the service's own sample scene with no file and no payment, then offers the next actions.
- Failure classification matches OOM as a word, so an error text containing "boom" or "zoom" is no longer reported as out of memory.

## 0.4.50 (2026-10-12)

- Auto top-up is offered when the credit is about to run out: after a final, if what is left (free credit plus balance) is below 100 JPY or below what that render cost, the reply carries autocharge_offer, at most once a week per key: what is left, what the last render cost, the settings (below 200 JPY, add 2,000 JPY, up to 10,000 JPY a month) and a link to a confirmation page. /v1/me, the billing reply and /start show it while the credit stays low. Keys that can still get the free card bonus are offered that first.
- MCP replies now pass the share thanks offer and the auto top-up offer to the agent, with an instruction to ask the user once after showing the result.

## 0.4.49 (2026-10-12)

- Getting ready to turn on the card model (a new key gets 100 JPY of free GPU time, and saving a card on a Stripe page that charges nothing adds 400 JPY more, once per card): keys made before the switch keep their welcome credit as it was, the card bonus lasts 14 days from when it is added, and it is not limited by the per-network daily cap.
- The page after saving a card says what happened: free GPU time added, or why not (prepaid cards and cards already used do not qualify, and such a card is not kept). If the card cannot be confirmed yet, nothing is charged and the free time is added later by a billing call or the webhook retry.
- While the card model is on, pages, guides, llms.txt and Markdown describe the welcome credit as up to 500 JPY, with the 100 JPY and 400 JPY split; the changelog keeps its history.

## 0.4.48 (2026-10-12)

- The public wording follows the welcome model: under a server setting, the one-line definition (facts.json, /facts, llms.txt), the pricing sentence, the pricing page, /v1/pricing (welcome_credit.card_bonus) and the JSON-LD offer state the cardless amount and the card bonus; under the default network model every text is unchanged.

## 0.4.47 (2026-10-12)

- A second welcome model, off by default: a new key gets 100 JPY of free GPU time once per network, and saving a card on a Stripe page that charges nothing adds 400 JPY more, once per card (prepaid cards do not qualify). The card is asked for only when the 100 JPY is used up: the 402, /v1/me, the MCP billing reply and /start then carry card_offer with the amount and the fact that nothing is charged. a server setting keeps today's 500 JPY per new key. The morning report names the model and the day's new keys, finished renders, paying keys and card registrations, so the two can be compared.
- The dollar figure names its source and the date it was checked.

## 0.4.46 (2026-10-12)

- A final longer than 240 frames is no longer refused: the service splits it into parts of 240 frames under one job id (b_...), and GET /v1/jobs/{id}, DELETE and the MCP render_status / render_download work on that id; each part is charged on its own GPU seconds and comes back as its own file (part-01_output.mp4, ...). One instruction takes up to 1,000 frames.
- A dollar figure for reference, when the operator sets a server setting and a server setting: /v1/me (balance), /v1/estimate (cost), /v1/pricing, the pricing page and the MCP billing reply show the amount in USD next to the yen, marked indicative; charges stay in JPY.

## 0.4.45 (2026-10-12)

- The BlendSwap comparison page is rebuilt on BlendSwap's own page as checked on 2026-10-11 (the price per GPU-hour and the Studio plan, rounding up and the two-credit minimum per job, L40S workers, 250 frames, 500 MB uploads, the bundled Blender versions, no free tier), with what ten previews and one finished scene cost here, and without the blocks it shared with other guides. It also says what we do not claim: no speed comparison between GPUs.
- The number of GPUs available right now, counted the same way as /v1/health, appears on the comparison page and the pricing page and updates itself when GPUs are added; a GPU on standby, shared with other work, is counted separately.
- Jobs charged from prepaid credit may render up to 4K (3840x2160); jobs covered by free time stay at 1080p. One job may use at most 10 GPU-hours, checked on the estimate before anything is held.
- tools/indexnow_daily.py sends IndexNow only the URLs whose sitemap date is today, once a day, instead of on every deploy.

## 0.4.44 (2026-10-12)

- Five use-case guides open with a measured table in one shape (machine or route, settings, GPU seconds, cost, round trip): 'Cycles is slow on my MacBook' puts a laptop CPU, the same laptop's GPU and the production GPU side by side on the same frame; 'AI-agent-generated 3D' shows one real loop from a prompt to a finished video with a real preview verdict; the GLB-to-MP4, product-turntable and product-shot guides show the one-command runs with their GPU seconds and prices.
- The citation panel now records whether JANCTION was the first service named in an answer (first-choice rate) and tags every question with its use case (no GPU, slow, GLB, product, agent, compare, developer); the morning report adds the first-choice rate and, per use case, the recommendation and first-choice rates. Four MCP/API duplicates were replaced by four use-case questions, so the panel stays at 52 questions.
- The morning report carries a weekly line for Bing's AI Performance (Copilot citations), kept by hand in aio/bing_ai.json.

## 0.4.43 (2026-10-12)

- Saved settings on /start: give the use, the light and the next step you took a name (for example 'white backdrop, square') and pick it at the top of the page next time. A public page's 'Try these settings on your own model' opens /start in the same use and light.
- Every guide starts with three lines: what it does, what it does not do, and the button to try it. The 'Blender is slow' and animation guides say what the cloud does not fix.
- The welcome credit is described the same way everywhere: a 500 JPY welcome credit for a new key, one per network every 30 days, further keys on the same network sharing what is left. A network shared by several people (a school, an office) is re-evaluated by hand: write to the contact address with the key prefix.
- After a first successful final render, an external key is told once that publishing the result as a listed public page earns 2,000 JPY of GPU credit after review. Public pages and the gallery say that creators may have received credit, and that the amount does not depend on what they say.
- Turntables and product shots ordered from /start are quoted at the outcome's fixed price ceiling, so the quote and the reservation agree; when the service answers that a job would reserve more than the quote, the page shows the service's number instead of asking again.
- A person who already has a key, or a network that created its new keys for the day, can paste the key at /start and continue. sitemap.xml never dates a page older than the pricing version it shows.
- Two guides were rebuilt without the blocks they shared with other pages: 'How to render Blender without a GPU' decides between your CPU, your own GPU, Colab, SheepIt, render farms and this service with the same scene measured on each (a laptop CPU, a laptop GPU and the production GPU, per frame); 'Blender cloud rendering, step by step' shows the real output of one command, a preview verdict, the wait and what you can send.

## 0.4.42 (2026-10-11)

- A browser page, /start, renders your own file without a connector, a CLI or a key you have to manage: choose a .blend, a 3D file or paste the bpy script an AI wrote; the scene is read first (missing files, cameras, frame range), the quote says whether the free GPU time covers it, the preview runs with max_yen 0 so nothing can be charged, and the result page offers the next step (change the light, four angles, a turntable, the animation as MP4, a high-quality still, the same settings on another file, a public page) with its price or 'no payment' before you press. Reloading returns to the last render. a server setting turns the page off without touching MCP, CLI or API.
- The guides open /start in the matching state (a GLB-to-MP4 page starts in turntable mode, an animation page in video mode, an AI page with the paste box), and the client guides carry the route for an AI without a connector: a prompt that makes it write the bpy script, which you paste at /start. The home page leads with 'No high-end GPU? Turn your 3D into images and video' and the two buttons.
- Estimates carry the breakdown a person decides with: covered_by_free_yen, from_credit_yen, max_charge_yen (the ceiling) and pricing_version; facts.json and /v1/pricing carry the same pricing version.
- Every scene records where it came from (upload, link, /upload drop, pasted script, or an operator sample) and jobs report input.own. The scorecard and the weekly metrics count 'first success with the user's own input', demo-only keys and repeat use on another day, and split money into credit consumed and free time covered.
- A daily budget for free GPU time across the service: when it is reached, new free jobs wait for the next day with a clear 429 while paid jobs run. Granted welcome credit is not reduced.
- POST /v1/ui/events records the browser funnel (landing, input, validation, quote, result, download, top-up) with short labels only; no file names, prompts or keys.
- The 'Blender is slow' guides start with a chooser: a slow final frame, an animation that never ends, out-of-memory, a slow viewport (fix locally; the cloud does not help there), simulations (not done here) and AI code that will not run each go to the right place. The agent-generated-3D guide lists, per app, how it connects and whether external users have actually rendered from it.

## 0.4.41 (2026-10-11)

- Errors carry code (AUTH_REQUIRED, INSUFFICIENT_CREDIT, COST_LIMIT_EXCEEDED, QUOTA_EXCEEDED, JOB_TOO_LARGE, MISSING_ASSET, WORKERS_UNAVAILABLE ...) and recommended_action (CONNECT, TOP_UP, ASK_USER, SPLIT_JOB ...) next to the existing error, detail and retryable, over the HTTP API and in MCP tool results. A failed job's failure also has category in the same words.
- max_yen on POST /v1/jobs and /v1/estimate: the most this one job may cost. A job that could cost more is refused before any credit is held (403 spend_cap_exceeded, scope request); the estimate says within_max_yen. The charge never exceeds the amount held, so a job that passes stays within max_yen.
- Estimates carry uncertainty: the GPU seconds the hold covers and how sure the estimate is (measured on this scene, on similar renders, or a default).
- CLI: estimate (time and price without rendering, exit 5 when over --max-yen), doctor (service, key, credit and the AI apps on this machine), login (saves a key without putting it in the shell history), billing (same as balance), --max-yen and --idempotency-key on render, --json for jobs and doctor.
- janction-render connect installs the plugin for Claude Code and Codex (the MCP server and the workflow skill together) and falls back to the MCP server alone when the plugin cannot be fetched.
- The plugin's skill was rewritten: when to use the service, how to tell the user it is not connected, the standard flow (preview, fix, estimate, ask, render, download), rules (no final without a preview, nothing paid without an estimate and a yes, no public share unless asked, no retry loops) and what to do for each error code, with examples and troubleshooting pages.
- The same plugin folder installs in Antigravity CLI (mcp_config.json). Each distribution channel tags its MCP URL (?src=claude-plugin, codex-plugin, antigravity-plugin, gemini-extension, and the connect command per app) so the service can tell which channel a key came from.
- A GitHub Action (integrations/github-action): a preview or a final render from a workflow, with a cost cap checked before the job and again by the service, an idempotency key from the run, cancel on timeout, and a job summary.
- Guessed paths go to the page that answers them (/integrations, /integrations/claude-code, /codex, /gemini, /cli, /docs, /about), and links with Japanese punctuation glued to them (、。）」) go to the page without it.

## 0.4.40 (2026-10-10)

- Product shots and turntables frame the object at its real size. Anything under a metre across was framed as if it were a metre, so a 26 cm bottle filled about a tenth of the frame; it now fills most of it, and very small objects (a 1.3 cm test) are not clipped by the camera.
- Product shots and turntables use a plain backdrop by default: the HDRI still lights the object but its photo (studio gear, a room) is no longer the background. environment_visible=true shows it again.
- The site's structured data no longer lists a price-0 offer; one per-GPU-second offer carries the welcome credit in its description (search summaries had read the site as free).
- New guide: Cycles is slow on my MacBook, what to do (Metal, settings that cut render time, and where to render instead, with times measured on the production GPU).
- The README shows real outputs from one-command samples on a public-domain GLB (four product shots, a 360-degree turntable, a .blend or script to MP4) with their GPU time and price, and a troubleshooting section.

## 0.4.39 (2026-10-10)

- When the credit does not cover a render, the 402 now says it in the units a person decides in: what this render costs (and the most it can cost; only GPU time actually used is charged), what the top-up adds and about how many renders like this it buys. tell_user is a ready sentence with the payment link for the agent to pass on; this_job_yen and renders_per_topup carry the numbers.
- A final submitted near the end of the free credit carries credit_note: about how much free credit is left and how many more renders like this it covers, what happens after (finals need prepaid credit from 500 yen; previews stay free; nothing is charged without a top-up), with a tell_user sentence. It appears when less than a fifth of the credit is left or fewer than three such renders still fit, at most once every six hours per key.
- A script refused only because it imports urllib, requests or http (usually an agent trying to fetch a model) is no longer counted toward revoking the key; the reply says to pass the file in asset_urls instead. Other refused scripts still count.
- The changelog pages say that prices in older entries were true for that release only.

## 0.4.38 (2026-10-10)

- GET /mcp asking for an event stream now gets 405 with Allow whether or not it carries a key (this stateless server has no standalone stream). A client that opened the stream without its token read the old 401 as 'sign in again', looped through the OAuth metadata and was rate-limited at the edge, which also blocked its real tool calls.
- The OAuth consent page states the current pricing (the welcome credit, then per GPU-second) in the same words as the site; it still described a daily free allowance.

## 0.4.37 (2026-10-10)

- A Render on JANCTION button for READMEs: https://render.janction.jp/badge.svg linking to /go?scene=<link to a 3D file>, a page that shows how to render that file from your own AI (the request already written), a terminal, MCP or the HTTP API. The page never fetches the file and is not indexed.
- The CLI takes an https link as the scene, and turns file-page links on GitHub and Hugging Face into raw links. New one-command outcomes: janction-render turntable <model> (a 360-degree MP4) and janction-render shots <model> (four PNGs, optionally transparent), with the price ceiling shown first.
- janction-render init also writes a Claude Code project skill (.claude/skills/janction-render/SKILL.md) when the project has a .claude folder; llms.txt routes models from AI 3D generators and links to models on GitHub or Hugging Face.

## 0.4.36 (2026-10-10)

- The local MCP server (pip install janction-render) has seven prompts that show up as slash commands: try it, render my scene, turntable video, product shots, scene from a description, .blend to MP4, and render within the free GPU time. It also reports its version in the handshake.
- janction-render connect lists the AI clients on this computer and adds JANCTION Render to one or all of them (it only adds its own entry and keeps a .bak); janction-render init writes agent instructions and the MCP setting into the current project.
- janction-render with no arguments shows how to start instead of an error, and janction-render try renders a sample scene in seconds and shows the free GPU time of the new key (uvx janction-render try needs no install). llms.txt now also routes users who want to render for free or from a terminal, CI or a headless server.
- Share, example and upload pages have links that open ChatGPT, Claude, Grok or Perplexity with the request already written; video share pages carry og:video; llms.txt shows calls from the OpenAI Responses API, the Anthropic MCP connector, Google ADK and Pydantic AI.
- The public numbers (/status and /v1/stats) split what used to be one 'other' bucket into direct API use (your own agents and apps), other MCP apps and the try page.

## 0.4.35 (2026-10-10)

- POST /v1/batches/{batch_id}/retry submits only the failed items of a batch again; items that rendered or are rendering are left alone, so nothing is drawn or charged twice. By default only failures that can succeed with the same input; failures caused by the script or file come back with the fix unless include_non_retryable is set. Up to 3 retries per item.

## 0.4.34 (2026-10-10)

- An asset sent again under the same name with different content (for example the same script with a new model.glb) is now rendered with the new content: the client compares assets by content as well as name, and the service no longer reuses frames or scene readings made before an asset changed. Scene views list each asset's sha256.
- An Idempotency-Key sent again with a different request (another scene or other settings) now gets 409 idempotency_key_reused, naming the job the key belongs to, instead of that job; the same request still returns the first job.

## 0.4.33 (2026-10-10)

- Welcome credit: keys made later on the same network can use what is left of that network's 500 JPY credit (the larger of that and their own 100 JPY), so reconnecting an app no longer strands the credit on the old key. A network still gets 500 JPY in total.

## 0.4.32 (2026-10-09)

- GET /v1/jobs/{id}/archive returns every file of a job in one zip (stored, not compressed; only=png,exr keeps those extensions), so a frame sequence is one request instead of hundreds that run into the rate limit (429). The Python client's download() uses it when there are 8 or more files and falls back to one file at a time on an older server.

## 0.4.31 (2026-10-09)

- render_review and review=true previews check all four sides: an object hidden behind a backdrop when the orbit camera comes round to the back, or cut or out of the shot at 90, 180 or 270 degrees, is reported with the angle and the fix (hide the backdrop from the camera with visible_camera = False; it still lights the scene).

## 0.4.30 (2026-10-09)

- README and llms.txt show how to call the service from your own agent or app: the Python client end to end (upload, render, wait, download), a webhook instead of polling, the OpenAI Agents SDK with a 120-second MCP timeout (the 5-second default cuts off render_preview) and LangChain.
- Credit holds follow real render times: a new scene's final is estimated from your recent finals, and the hold is lowered while it renders. /v1/me, billing() and a 402 show held_yen, the credit held by jobs that are still rendering.
- Scenes and results of keys that have topped up stay 7 days after last use (24 hours for other keys).
- Free renders keep at least one GPU slot while paid renders are queued.
- /mcp answers directory and uptime checkers' list calls without a key; unknown /v1 paths return JSON that points to the API's main calls, /openapi.json, /llms.txt and /mcp (405 with Allow when only the method is wrong).

## 0.4.29 (2026-10-09)

- The PyPI page lists classifiers (3D Rendering, Artificial Intelligence, Python 3.11 to 3.13), the MIT license and links to the fact sheet, llms.txt, pricing and the changelog; the README links are absolute, so they also work on PyPI.

## 0.4.28 (2026-10-09)

- render_review, a new tool in the stdio MCP server: it checks a 3D model or a generated scene from 4 sides (0, 90, 180 and 270 degrees) under studio light and returns pass / warning / fail, a score, the checks it ran with fix code, and the 4 views in one image. Over HTTP: POST /v1/jobs with kind=preview and review=true. The hosted MCP server (/mcp) gets it in a later update.
- Previews catch two more problems: image files that cannot be found (they render black or pink) and objects hidden behind a floor, wall or backdrop. Both come back as fix in the critic with the code to fix them, and the suggested camera now also turns the camera toward the objects.
- jr_assets.frame_camera() no longer moves a camera left at the origin under the objects to below the floor; it gets a 3/4 view from above.
- scene_info returns next and preview_args: a render_preview call sized to the scene's shape (a vertical 1080x1920 scene gets a 404x720 preview instead of the default 1280x720), four frames for an animation, a studio light for a scene with no light.

## 0.4.27 (2026-10-09)

- The package description, the plugins and the listings lead with what is free: up to 500 JPY of GPU time per new key (the welcome credit), then 0.1 JPY per GPU-second. The old "10 free GPU-minutes a day" wording is gone from the package files.
- Payment pages open in English with a 日本語 switch at the top right. The Stripe payment page opens in the language of the page the button was pressed on, and you come back to a page in the same language.
- A 500 JPY top-up first shows a page to pick 500, 2,000, 5,000 or 10,000 JPY, with the credit each one adds and its bonus, and the two monthly plans. Opening the page creates nothing; the one you press opens Stripe.
- Final renders reuse frames that the same key has already rendered from the same scene with the same settings: those frames are copied without GPU time and only the rest is rendered. Rendering 1-96, 1-120 and 1-144 of one scene now costs about the same as rendering 1-144 once. Progress counts the copied frames.
- A job counts as free only when 1.5 times its estimate fits in the free GPU time left, because a render can run past its estimate; otherwise credit is held for the part that may go past the free time and only time actually used past it is charged. Estimates and 402 payment_required say so.
- Estimates for scenes known only from short previews are closer to the real time (finals estimated at less than two thirds of their actual GPU time dropped by more than half in a 14-day backtest).
- Blender add-on 0.1.4 (/extensions/index.json): the 402 line and the Estimate tooltip speak of the free GPU time instead of today's. The track record on the home page and /status counts outside use only.

## 0.4.26 (2026-10-08)

- Auto top-up: save a card once on the Stripe page, and when the balance drops below a threshold (default 200 JPY) the card adds a set amount (default 2,000 JPY, which gives 2,200 JPY of credit). A job that would run short is topped up on the spot instead of getting 402, so an agent's work does not stop. At most 10,000 JPY a month and 3 times a day by default; a card problem pauses it and says why; turn it off at any time. POST /v1/billing/autocharge, POST /v1/billing/autocharge/off, GET /v1/billing/autocharge.
- Monthly plans as a monthly top-up: Starter 2,980 JPY a month adds 3,500 JPY of credit, Pro 9,800 JPY adds 12,000 JPY. Unused credit carries over and the price per GPU-second stays the same. Cancel at any time; the plan runs to the end of the paid month. POST /v1/billing/subscribe, POST /v1/billing/subscription/cancel, POST /v1/billing/portal (the Stripe billing page), GET /v1/billing/plans.
- billing() (remote and stdio) shows the auto top-up and monthly plan status with links the user opens: a confirmation page first, then Stripe. Agents cannot subscribe, cancel or turn auto top-up on by themselves.
- The terms and the legal notice cover automatic renewal and auto top-up; the pricing page, /v1/pricing, /facts and llms.txt list the plans and the auto top-up defaults.

## 0.4.25 (2026-10-08)

- Welcome credit: each new key starts with 500 JPY of free GPU time (5,000 GPU-seconds) for 14 days, covering previews and finals; one full credit per network every 30 days, further keys from the same network get 100 JPY. Keys that already existed get the same 500 JPY for 14 days from the switch. After the welcome credit is used up or expires, previews stay free up to 2 GPU-minutes a day and finals cost 0.1 JPY per GPU-second from prepaid credit; the first top-up during the 14 days counts 1.5x (bonus up to 500 JPY). This replaces the 10 free GPU-minutes a day.
- Top-ups: from 500 JPY, with a bonus on larger amounts (2,000 JPY gives 2,200 JPY of credit, 5,000 gives 5,750, 10,000 gives 12,000); the first top-up in the welcome period counts 1.5x with the bonus capped at 500 JPY, and the larger of the two bonuses applies. The payment page says how much credit you get, `402 payment_required` lists the options (`topup_options`, `topup_credit_yen`) and `GET /v1/pricing` has them under `topup`. The planned monthly plans (Starter, Pro, Scale) are withdrawn.
- `billing()` (remote and stdio) returns the welcome balance and expiry and says when it is running out; `402 payment_required` and estimates carry the welcome balance; the stdio package's instructions, the Blender add-on 0.1.3 and the Maya / Houdini / Cinema 4D tools describe the welcome credit.
- Service: a second isolation layer added to the render sandbox.
- Service: when Blender 5.0's importer fails on an uploaded 3D file and the job did not ask for a Blender version, the same chunk is retried once with Blender 5.2 (`params.blender_auto` says so); if 5.2 fails too, the failure says to re-export the file. Importer crashes are reported as `IMPORTER_ERROR` instead of a script error.
- Service: a refund made on Stripe (`charge.refunded`) takes the refunded amount back out of the key's credit once, matched to the payment by its PaymentIntent; credit already spent on renders cannot be taken back and is reported to the operator. `tools/stripe_check.py --sync-events` adds the refund event to an existing webhook.
- Service: `billing()` on the remote MCP checks the key's open checkouts with Stripe and credits paid ones, so a payment counts even when the webhook is late; job results carry `cost.free_gpu_seconds` (the part covered by the free daily time); the payment page tells chat users (Claude, ChatGPT) to go back to their agent; the operator gets a Slack line per credited payment and a billing line in the daily report.
- Blender add-on 0.1.2 (`/extensions/index.json`): when a render goes past today's free GPU time without enough credit, the panel says how much credit it needs and shows an **Open top-up page** button (Stripe Checkout in the browser); after paying, press the same button again. The add-on's own version string (User-Agent) now matches the manifest.

## 0.4.24 (2026-10-08)

- The README (PyPI, GitHub, Glama), the Claude Code plugin description, the Cursor rule, the Blender add-on and the Maya / Houdini / Cinema 4D submit tools describe the free daily GPU time (10 GPU-minutes per key) and the price beyond it (0.1 JPY per GPU-second); the `billing()` row of the tools table was still "free-beta quota".
- Blender add-on 0.1.1 (`/extensions/index.json`, `janction_render-0.1.1.zip`): wording only — tagline, key tooltip, final-render tooltip and the per-job limit notes.
- `tests/test_live_wording.py` also reads README.en.md, the plugin, the add-on and the DCC tools.

## 0.4.23 (2026-10-08)

- Paid use started on 2026-10-08 (a server setting). Each key keeps its free GPU-minutes per day (10, or 20 per network): a job that fits the time left today is free, and a job that goes past it reserves and is charged only for the GPU seconds beyond the free time, at 0.1 JPY per GPU-second from prepaid credit (Stripe Checkout, from 500 JPY). A 402 `payment_required` says how much of the job the free time covers (`free_gpu_seconds_left_today`, `estimated_gpu_seconds`).
- `POST /v1/estimate` and `render_estimate` count today's free time in paid mode: `cost.free`, `cost.estimated_yen` (what will be charged), `cost.billable_gpu_seconds`, `cost.free_gpu_seconds_left_today`, `cost.list_price_yen` (the whole job without the free time) and `quota` with `fits_today`. Before, a job that fit the free time was quoted at its full price with `enough_balance: false`.
- `billing()` (remote and stdio MCP) returns `mode: free_allowance` with today's free GPU time and the credit; before, paid mode still answered `free_beta` with "no charges". `render_estimate` and the 402 reply tell the agent to state the price and show `checkout_url` before going past the free time.
- Paid jobs keep the per-job limits (240 frames, 1920x1080 pixels, `400 beta_limit`); before, they applied only in the free beta.
- MCP instructions and `render_final`: the limits name the free daily time and the price per GPU-second (the instructions stay under 1,800 characters).
- Site: `/pricing` and `GET /v1/pricing` (`status: paid`, `price`), products, facts, llms.txt, auth.md, the legal notice (the free daily time in the price row; the phone line reads "disclosed without delay on request"), the terms' last-updated date and every guide describe the free daily time and the price. The definition sentence ends with "10 free GPU-minutes a day, then 0.1 JPY per GPU-second; operated by JasmyLab Inc." The monthly plans are not on sale yet.
- `tests/test_live_wording.py` renders every page in paid mode and fails on free-beta wording.
- `/benchmarks` adds two of Blender's own demo files rendered at fixed settings (frames 1-3, 1920x1080, 128 samples, denoising on, Blender 5.2): Classroom (CC0) at 8.93 GPU seconds per frame and Barcelona Pavillion (CC-BY) at 10.55, that is 0.89 and 1.05 JPY per frame at 0.1 JPY per GPU-second. The zip URLs, their sha256 and `scripts/bench_same_scene.py` let anyone render the same files with the same settings on another GPU or service and compare; the numbers are also in `/benchmarks.json` (`same_scene`).
- `examples/blender-mcp/`: build in Blender with a Blender MCP server (ahujasid's mcp-for-blender or Blender's Lab MCP server) and render with JANCTION Render, handing over a saved .blend (your camera and lights) or a GLB (product shot or turntable). `verify_handoff.py` checks both hand-offs without opening Blender's window.

## 0.4.22 (2026-10-08)

- The README (GitHub, PyPI, Glama) links to the guides on the official site: rendering Blender without a GPU, Claude Code / Codex / Cursor / ChatGPT with Blender, the Blender MCP server, the comparison of render farms for AI agents, headless Blender as an API, glTF to MP4, product turntables, costs and examples.
- The MCP tools (remote and stdio) pass the new quota fields on (`gpu_seconds_left_today`, `fits_frames`, `suggested`) and their `next` names the frame range that still fits today.
- The service records which remote MCP tool returned which error (tool, error code and status, no request content), so failed calls from Claude.ai / ChatGPT users show up in the operator's daily report.
- A `quota_exceeded` 429 now says how much still fits today: `gpu_seconds_left_today`, `seconds_per_frame_estimate`, `fits_frames` and, for a final render, `suggested` (`frame_start`/`frame_end`). An agent splitting a long animation no longer has to shrink the range by trial and error.
- A final render whose frames overlap a queued, running or finished job of the same scene with the same settings comes back with `overlaps` and a `note` (and in `render_final`'s `next`), so the agent can cancel it instead of rendering the same frames twice. It is still queued.
- The preview critic measures blown-out highlights inside the subject, not across the whole frame. A white background is fine: a product or reference shot on white is no longer told to lower its lights (on 2026-10-08 six previews with a white world and the subject at 27% of the frame were all marked `fix: blown_out`, and the agent kept re-rendering). A small subject on a white background gets `check` instead of `fix`. Re-judging the 74 previews still on the service changed only those seven.
- Artifacts are easier to receive. `GET /v1/jobs/{id}` now gives every artifact a `view_url` (a signed link that opens without a key until the render expires) for API keys too, not only for remote MCP; a keyless request for `/v1/jobs/{id}/artifacts/{name}` answers 401 with that hint; `/v1`, `/api` and `/api/v1` return the API index instead of 404.
- Opening a signed link (`/dl/...`) now counts as a download in the operator's funnel, so remote MCP users who take their renders through links are no longer counted as never downloading.
- Estimates match measured render times: samples barely change the time per frame (adaptive sampling and denoising), so a frame now scales with `(samples / 128) ** 0.1` instead of linearly, and the fixed cost per chunk is 2 s instead of 5 s. Replayed on the last 14 days of final renders, the median estimate went from 1.52x to 1.04x the actual GPU time and the share within 0.67x to 1.5x from 35% to 72%. a server setting and a server setting restore the old values.

## 0.4.21 (2026-10-08)

- Every preview returns a critic verdict (`ok` / `check` / `fix`), a score and `issues`, each with fix code (a bpy line or a tool setting): too dark, blown out, no light, nothing in view, the camera inside an object, objects cut by the frame edge. The image is measured on the service and the scene is counted in Blender before rendering; when something needs fixing, the `next` hint asks the agent to apply it and preview again before a final render. a server setting turns it off on a self-hosted server.
- `jr_assets.frame_camera(margin=1.1)` in a scene script points the camera at every object and fits them in the frame, keeping its direction.
- MCP tool texts, version 2: instructions of about 1,600 characters (clients were cutting the old ones at about 2,000) that open with when to use, when not to use and the first call; a description on every tool parameter; `render_preview` listed first; long jobs are described as rendered in chunks, and the per-call wait as 50 s. The stdio server uses them by default; a server switches with a server setting.
- New page: Best render farms for AI agents (2026), `/best-render-farms-for-ai-agents` (English, Japanese, `.md`), with sources and where JANCTION Render is not the right pick.
- The consent page and `POST /v1/keys` take an optional `found_via` (where the user found the service).
- `samples/cube_scene.py` keeps every object in frame on all 24 frames (the critic flagged the first-call sample).
- The product description gained one sentence about the critic (README, site, llms.txt, /facts).
- GPU lanes for many workers: a worker can declare a server setting or a server setting prefix>`. Previews and scene reads go to the preview lane and never wait behind long finals; finals are taken paid first, then free, then internal, with a per-key fair share (a server setting, default 3); a reserved worker only serves its key. No lane starves: final workers pick up previews that waited a server setting (2 s) and preview workers take finals when no final worker is online. Workers without lanes behave exactly as before. `/v1/health` reports `lanes` (workers, busy, queued chunks, oldest wait).
- Final renders are split across the online final workers (a server setting keeps chunks long enough that Blender's start-up cost does not dominate; a server setting stays the upper bound). Estimates count the workers of the job's lane, and a preview's queue wait no longer includes queued finals.
- Workers on other GPU hosts can connect through the public URL: a chunk's frames can be sent ahead in parts (`POST /v1/worker/chunks/{id}/frames`) to stay under the 100 MB request cap; `deploy/worker-host/` sets up one worker per GPU (Blender 5.0/5.2 images from the Dockerfile, HDRIs, env per GPU, start/stop/watchdog).
- Batch API: `POST /v1/batches` takes up to 100 items (`scene_url` or `scene_id`, an outcome such as `turntable` or job params, optional `notify_url`) and returns a `batch_id` at once; items are fetched and submitted in the background with per-item errors and an Idempotency-Key; `GET /v1/batches/{id}` shows each item's job status.
- Scorecard and the morning report: preview queue wait and round trip p50/p95, Blender start-up p50 (from per-stage timings the workers now report), final start wait, chunks per job, which lane served each chunk.
- Receptionist hardening after the 10/7 stall (a synchronous URL fetch ran on the event loop and the service waited 120 s on itself): URL fetches (`scene_url`, `asset_urls`) now run in their own small thread pool with per-key and global concurrency caps (`429 fetch_busy`; a server setting 8, a server setting 2) and a total-time deadline per download (a server setting, 300 s); job submission and USDC top-ups run off the loop too; the shared thread limiter is raised (a server setting, 120) and one key holds at most a server setting (4) in-call waits at a time; an event-loop watchdog logs `event loop stalled for N s`, records `loop_stall` and reports `loop` in `/v1/health` (tools/watch.py alerts on it). A test forbids blocking network calls inside async routes.
- The same class, second instance (found 10/8): when the last chunk of a final arrived, the video assembly (ffmpeg for MP4 / WebM / ProRes) and the preview contact sheet ran on the event loop inside the worker's completion call, so a long 1080p final could freeze the receptionist for tens of seconds. Both now run in a thread, as do the GLB-optimization check and its before/after image. The test's forbidden list now also covers the assembly helpers, PIL, subprocess and shutil, and a new test checks `/v1/health` stays fast while a video is assembled.
- Operator checks follow "never exercise a new path for the first time on production": `tools/guarded_probe.py --local` starts a throwaway receptionist (temporary data, Slack and Stripe off) with `tools/fake_worker.py` (no GPU; returns test images through the real worker API) and runs the check; the same check (same command and script contents) may then run on production for 14 days, watched — `/v1/health` is polled every second and the check is stopped when it turns slow or the event loop stalls. Checks that cannot run locally need `--first-on-prod "<reason>"`. The morning smoke (`tools/aio_daily.py`) sends the sample as a file even with a throwaway `--base`, and revokes the key it created when run through the guard. A check the guard stopped on production is refused there until it passes locally again (no second stop). The test suite now runs every event loop in asyncio debug mode and fails any test that blocks a loop for 0.5 s or more, and the static check also covers the calls flake8-async looks for (urllib, httpx, socket, os.system). Runbook: docs/35 §7; competitor and industry survey: docs/37.

## 0.4.20 (2026-10-07)

- Feedback in one click: a finished final render carries `feedback_url` (signed, no login, valid 7 days) where the user can say whether the result was what they asked for and leave a line; the same short form sits under every share page; `POST /v1/jobs/{id}/feedback` for API and CLI users. Quotes the user allowed and the operator approved appear at `/reviews.json` and under "What users say" on `/examples` (schema.org Review). No IP addresses are stored.
- Directory crawlers and health checks (known user agents, no key) now get `initialize`, `tools/list` and `ping` without a key, so listings can read the tool list; `tools/call` still requires a key and real clients still start OAuth from the 401 (a server setting, a server setting).
- The remote MCP waits at most 50 s inside one call (was 80 s; a server setting), below the tool timeouts of common clients; the hints say `render_download(job_id, wait_seconds=45)`.
- Scorecard: a per-client table (keys, previews, finals, final rate, downloads, GPU minutes), the feedback counts and the latest comments, and how many directory probes were answered without a key.
- 502s fixed at the source: the stateless receptionist no longer advertises or serves `subscriptions/listen` (protocol 2026-07-28; Claude.ai opened it after every initialize and the stream died at once), and an authenticated `GET /mcp` (the standalone SSE stream that Claude Code and mcp-remote try) now gets a clean 405 with `Allow` instead of an aborted response. Both showed up as 502 at the CDN.
- Tool descriptions start with when a local render is the better choice (a local Blender MCP for editing an open scene; a single still on a machine with its own GPU); the instructions point to `/examples` for ready-made scenes.
- The stdio package defaults to the public service: `JANCTION_RENDER_SERVER` is `https://render.janction.jp` unless set (a local dev server is `http://127.0.0.1:8340`); the unreachable-server hints changed accordingly.
- Server card: every tool carries its annotations (readOnlyHint, destructiveHint, idempotentHint, openWorldHint).
- Every guide has a Markdown URL: `/<slug>.md` and `/ja/<slug>.md`.
- Six new guides for buyers' questions: `/blender-render-cost`, `/product-turntable`, `/gltf-to-mp4`, `/blender-headless-api`, `/janction-vs-rebusfarm`, `/for-teams` (English and Japanese, numbers from production renders and public pages read on 2026-10-07).
- Examples: one page per rendered example at `/examples/<id>` (image or video, prompt, settings, GPU seconds, the full bpy script; Markdown with `.md`), listed in the sitemap and llms-full.txt; ten more sample scenes (architecture, logo animation, bar chart, scattered spheres, three-camera product shots, jewelry, sci-fi corridor, low-poly forest, terrain, packaging) rendered by the night batch.
- Scorecard: calls by `clientInfo.name` and protocol version, keys that exhausted the daily quota (billing prospects).
- Hotfix (hosted service, same evening): `POST /v1/files/url` and `POST /v1/files/{id}/assets/urls` fetched URLs synchronously inside async handlers and could stall the whole receptionist for up to 120 s; a scene_url pointing at the service's own `/samples/` always did. Fetches now run in a worker thread and own samples are read from disk.
- Site consistency: the tool tables on the top page and the MCP guide list all 12 tools (`render_share` / `render_unshare` and `asset_search` were missing); EEVEE (`engine='eevee'`) and the EXR / WebM / ProRes outputs are named on the top page, in llms.txt and in the FAQ; "split across GPUs" became "rendered in chunks" (one GPU during the beta); the Japanese connect table now matches the English one (Gemini CLI, Grok, Perplexity, Le Chat, Windsurf / Cline / Goose) and facts.json `supported_clients` lists Grok, Perplexity and Le Chat.

## 0.4.19 (2026-10-07)

- Several cameras in one job: `cameras=['Front','Top','Iso']` (up to 8) renders the same frame from each named camera. A preview tiles them in one labeled sheet; a final returns one PNG/EXR per camera and `camera_files` maps names to files. For product shots from fixed angles instead of one job per camera.
- After every finished preview the tools return `final_estimate` (how long the same scene takes as a 1080p final) and `quota_left_today`; the `next` hint says whether it fits today's free quota.
- Source of a key is recorded: add `?src=<listing>` to the MCP URL (`https://render.janction.jp/mcp?src=smithery`), pass `source` to `POST /v1/keys`, or let the OAuth `resource` carry it. It appears in `jobs.jsonl` and in the scorecard (`by_source`).
- Consent page: optional email (quota notices and new features only). Operators can raise one key's daily free quota.
- stdio MCP: `scene_url` (an https link, e.g. the sample cube scene) like the remote tools; `POST /v1/files/url` for the HTTP API; the instructions suggest a first call with the sample scene and `environment='compare'`.
- Tool definitions: every parameter has a description; the stdio tools carry annotations (read-only / destructive / idempotent) like the remote server.
- Site: share pages show the MCP URL; the BlendSwap comparison states that both services offer a public MCP; the old repository path was removed from `facts.json`; operator probes and directory health checks are excluded from the scorecard.

## 0.4.18 (2026-10-06)

- Client: when the server cannot be reached (connection refused, DNS failure, timeout), the MCP tools and the CLI return `server_unreachable` with the target URL and a fix hint instead of a bare transport error (set `JANCTION_RENDER_SERVER=https://render.janction.jp` when the default local URL is in use); `bad_server_url` for a malformed `JANCTION_RENDER_SERVER`. No service change.

## 0.4.17 (2026-10-05)

- One definition sentence across PyPI, the MCP Registry, the plugin manifests, README and the site; no client code change since 0.4.16.
- Service: pricing page and `GET /v1/pricing`, changelog page and Atom feed, public usage statistics (`GET /v1/stats`, shown on /status), machine-readable error hints (`possible_fix`, `docs_url`, `retryable`), estimates carry `currency` and `expires_at`.
- Site: guides for Cursor, VS Code, Windsurf, Gemini CLI / Antigravity, 3D files and a BlendSwap comparison; connection rows for Grok, Perplexity, Le Chat, Cline and Goose; FAQ extended; GA4 behind a nonce-based CSP.
- Service (later the same day): spending caps per key (`GET /v1/me` → `limits`, `POST /v1/me/limits`; an over-cap job is refused with `403 spend_cap_exceeded` before anything is reserved), `Idempotency-Key` on `POST /v1/jobs` and `/v1/outcomes`, `Retry-After` on 429, fixed-price outcomes (`GET /v1/outcomes`, `POST /v1/outcomes/turntable|product-shot`: the quoted `price_yen` is a ceiling). CLI: `limits`, `outcomes`. Cursor project rule in `integrations/cursor/`.

## 0.4.16 (2026-10-03)

- Task API: `POST /v1/tasks`, `GET /v1/tasks/{id}` (task `glb_optimize`).
- OAuth registrations from known directories handled separately; jobs record the submitting app.
- Estimates show `list_price_yen` at the planned price during the free beta; MCP server card at `/.well-known/mcp/server-card.json`.

## 0.4.15 (2026-10-02)

- External security review closed: every finding fixed and re-tested.

## 0.4.10 - 0.4.14 (2026-10-02)

- Runtime audit hook plus static check for scripts (processes, sockets, ctypes, dynamic imports).
- OAuth: per-client key cap, token expiry (30 days) and revocation, tighter CORS and dynamic registration, `redirect_uri` checks; glTF reference paths checked; NaN rejected.

## 0.4.9 (2026-10-01)

- HTTPS enforced (HSTS); key issuance rate-limited; internal host names removed from health; package author JasmyLab Inc.

## 0.4.2 (2026-10-01)

- Transparent backgrounds, GIF and WebP outputs, `notify_url` on final renders; MCP tool descriptions fixed.

## 0.4.1 (2026-10-01)

- Wait estimates while the GPU is lent out (gate) in health, estimates, status and MCP hints.

## 0.4.0 (2026-10-01)

- Environment presets, 3D file import (glTF/GLB, FBX, USD, OBJ, STL, PLY, Alembic), orbit turntables, EEVEE, MCP Apps panel, Blender 5.2 option.
- Japanese pages, `llms-full.txt`, IndexNow; Blender add-on and Maya / Houdini / Cinema 4D tools.

## 0.3.0 (2026-09-30)

- Remote MCP server (Streamable HTTP, OAuth 2.1 with dynamic client registration), `asset_search` (CC0 Poly Haven), share pages and gallery, benchmarks and status pages.

## 0.2.1 (2026-09-30)

- First public beta on PyPI and the official MCP Registry: stdio MCP server, CLI and HTTP API.
