# Changelog

The live, per-version list is at https://render.janction.jp/changelog (Atom: https://render.janction.jp/changelog.xml). Versions are the PyPI releases of `janction-render`; the hosted service follows the same numbers.

## Unreleased

## 0.4.22 (2026-10-08)

- The README (GitHub, PyPI, Glama) links to the guides on the official site: rendering Blender without a GPU, Claude Code / Codex / Cursor / ChatGPT with Blender, the Blender MCP server, the comparison of render farms for AI agents, headless Blender as an API, glTF to MP4, product turntables, costs and examples.
- The MCP tools (remote and stdio) pass the new quota fields on (`gpu_seconds_left_today`, `fits_frames`, `suggested`) and their `next` names the frame range that still fits today.
- The service records which remote MCP tool returned which error (tool, error code and status, no request content), so failed calls from Claude.ai / ChatGPT users show up in the operator's daily report.
- A `quota_exceeded` 429 now says how much still fits today: `gpu_seconds_left_today`, `seconds_per_frame_estimate`, `fits_frames` and, for a final render, `suggested` (`frame_start`/`frame_end`). An agent splitting a long animation no longer has to shrink the range by trial and error.
- A final render whose frames overlap a queued, running or finished job of the same scene with the same settings comes back with `overlaps` and a `note` (and in `render_final`'s `next`), so the agent can cancel it instead of rendering the same frames twice. It is still queued.
- The preview critic measures blown-out highlights inside the subject, not across the whole frame. A white background is fine: a product or reference shot on white is no longer told to lower its lights (on 2026-10-08 six previews with a white world and the subject at 27% of the frame were all marked `fix: blown_out`, and the agent kept re-rendering). A small subject on a white background gets `check` instead of `fix`. Re-judging the 74 previews still on the service changed only those seven.
- Artifacts are easier to receive. `GET /v1/jobs/{id}` now gives every artifact a `view_url` (a signed link that opens without a key until the render expires) for API keys too, not only for remote MCP; a keyless request for `/v1/jobs/{id}/artifacts/{name}` answers 401 with that hint; `/v1`, `/api` and `/api/v1` return the API index instead of 404.
- Opening a signed link (`/dl/...`) now counts as a download in the operator's funnel, so remote MCP users who take their renders through links are no longer counted as never downloading.
- Estimates match measured render times: samples barely change the time per frame (adaptive sampling and denoising), so a frame now scales with `(samples / 128) ** 0.1` instead of linearly, and the fixed cost per chunk is 2 s instead of 5 s. Replayed on the last 14 days of final renders, the median estimate went from 1.52x to 1.04x the actual GPU time and the share within 0.67x to 1.5x from 35% to 72%. `JR_SAMPLES_EXPONENT` and `JR_SEC_PER_CHUNK_OVERHEAD` restore the old values.

## 0.4.21 (2026-10-08)

- Every preview returns a critic verdict (`ok` / `check` / `fix`), a score and `issues`, each with fix code (a bpy line or a tool setting): too dark, blown out, no light, nothing in view, the camera inside an object, objects cut by the frame edge. The image is measured on the service and the scene is counted in Blender before rendering; when something needs fixing, the `next` hint asks the agent to apply it and preview again before a final render. `JR_CRITIC=0` turns it off on a self-hosted server.
- `jr_assets.frame_camera(margin=1.1)` in a scene script points the camera at every object and fits them in the frame, keeping its direction.
- MCP tool texts, version 2: instructions of about 1,600 characters (clients were cutting the old ones at about 2,000) that open with when to use, when not to use and the first call; a description on every tool parameter; `render_preview` listed first; long jobs are described as rendered in chunks, and the per-call wait as 50 s. The stdio server uses them by default; a server switches with `JR_TOOLDOCS=new|old`.
- New page: Best render farms for AI agents (2026), `/best-render-farms-for-ai-agents` (English, Japanese, `.md`), with sources and where JANCTION Render is not the right pick.
- The consent page and `POST /v1/keys` take an optional `found_via` (where the user found the service).
- `samples/cube_scene.py` keeps every object in frame on all 24 frames (the critic flagged the first-call sample).
- The product description gained one sentence about the critic (README, site, llms.txt, /facts).
- GPU lanes for many workers: a worker can declare `JR_LANES=preview|final|spare` or `JR_RESERVED_FOR=<key prefix>`. Previews and scene reads go to the preview lane and never wait behind long finals; finals are taken paid first, then free, then internal, with a per-key fair share (`JR_FREE_PARALLEL_PER_KEY`, default 3); a reserved worker only serves its key. No lane starves: final workers pick up previews that waited `JR_PREVIEW_SPILL_S` (2 s) and preview workers take finals when no final worker is online. Workers without lanes behave exactly as before. `/v1/health` reports `lanes` (workers, busy, queued chunks, oldest wait).
- Final renders are split across the online final workers (`JR_CHUNK_MIN_S` keeps chunks long enough that Blender's start-up cost does not dominate; `JR_FRAMES_PER_CHUNK` stays the upper bound). Estimates count the workers of the job's lane, and a preview's queue wait no longer includes queued finals.
- Workers on other GPU hosts can connect through the public URL: a chunk's frames can be sent ahead in parts (`POST /v1/worker/chunks/{id}/frames`) to stay under the 100 MB request cap; `deploy/worker-host/` sets up one worker per GPU (Blender 5.0/5.2 images from the Dockerfile, HDRIs, env per GPU, start/stop/watchdog).
- Batch API: `POST /v1/batches` takes up to 100 items (`scene_url` or `scene_id`, an outcome such as `turntable` or job params, optional `notify_url`) and returns a `batch_id` at once; items are fetched and submitted in the background with per-item errors and an Idempotency-Key; `GET /v1/batches/{id}` shows each item's job status.
- Scorecard and the morning report: preview queue wait and round trip p50/p95, Blender start-up p50 (from per-stage timings the workers now report), final start wait, chunks per job, which lane served each chunk.
- Receptionist hardening after the 10/7 stall (a synchronous URL fetch ran on the event loop and the service waited 120 s on itself): URL fetches (`scene_url`, `asset_urls`) now run in their own small thread pool with per-key and global concurrency caps (`429 fetch_busy`; `JR_FETCH_THREADS` 8, `JR_FETCH_PER_KEY` 2) and a total-time deadline per download (`JR_FETCH_DEADLINE_S`, 300 s); job submission and USDC top-ups run off the loop too; the shared thread limiter is raised (`JR_THREAD_TOKENS`, 120) and one key holds at most `JR_MCP_WAITS_PER_KEY` (4) in-call waits at a time; an event-loop watchdog logs `event loop stalled for N s`, records `loop_stall` and reports `loop` in `/v1/health` (tools/watch.py alerts on it). A test forbids blocking network calls inside async routes.
- The same class, second instance (found 10/8): when the last chunk of a final arrived, the video assembly (ffmpeg for MP4 / WebM / ProRes) and the preview contact sheet ran on the event loop inside the worker's completion call, so a long 1080p final could freeze the receptionist for tens of seconds. Both now run in a thread, as do the GLB-optimization check and its before/after image. The test's forbidden list now also covers the assembly helpers, PIL, subprocess and shutil, and a new test checks `/v1/health` stays fast while a video is assembled.
- Operator checks follow "never exercise a new path for the first time on production": `tools/guarded_probe.py --local` starts a throwaway receptionist (temporary data, Slack and Stripe off) with `tools/fake_worker.py` (no GPU; returns test images through the real worker API) and runs the check; the same check (same command and script contents) may then run on production for 14 days, watched — `/v1/health` is polled every second and the check is stopped when it turns slow or the event loop stalls. Checks that cannot run locally need `--first-on-prod "<reason>"`. The morning smoke (`tools/aio_daily.py`) sends the sample as a file even with a throwaway `--base`, and revokes the key it created when run through the guard. A check the guard stopped on production is refused there until it passes locally again (no second stop). The test suite now runs every event loop in asyncio debug mode and fails any test that blocks a loop for 0.5 s or more, and the static check also covers the calls flake8-async looks for (urllib, httpx, socket, os.system). Runbook: docs/35 §7; competitor and industry survey: docs/37.

## 0.4.20 (2026-10-07)

- Feedback in one click: a finished final render carries `feedback_url` (signed, no login, valid 7 days) where the user can say whether the result was what they asked for and leave a line; the same short form sits under every share page; `POST /v1/jobs/{id}/feedback` for API and CLI users. Quotes the user allowed and the operator approved appear at `/reviews.json` and under "What users say" on `/examples` (schema.org Review). No IP addresses are stored.
- Directory crawlers and health checks (known user agents, no key) now get `initialize`, `tools/list` and `ping` without a key, so listings can read the tool list; `tools/call` still requires a key and real clients still start OAuth from the 401 (`JR_MCP_PUBLIC`, `JR_MCP_PUBLIC_UA`).
- The remote MCP waits at most 50 s inside one call (was 80 s; `JR_MCP_WAIT_S`), below the tool timeouts of common clients; the hints say `render_download(job_id, wait_seconds=45)`.
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
- Consent page: optional email (quota notices and new features only). Operators can raise one key's daily free quota (`tools/keys_admin.py set-quota`).
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

- External security review closed: worker file-read bypass closed (read-only root filesystem, loader restrictions), `notify_url` validated at submission, dynamic client registration limited per origin, client names sanitised.

## 0.4.10 - 0.4.14 (2026-10-02)

- Runtime audit hook plus static check for scripts (processes, sockets, ctypes, dynamic imports).
- OAuth: per-client key cap, token expiry (30 days) and revocation, tighter CORS and dynamic registration, `redirect_uri` checks; glTF reference paths checked; NaN rejected.

## 0.4.9 (2026-10-01)

- HTTPS enforced (HSTS); key issuance limited per network (IPv6 /64); internal host names removed from health; package author JasmyLab Inc.

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
