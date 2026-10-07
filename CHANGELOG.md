# Changelog

The live, per-version list is at https://render.janction.jp/changelog (Atom: https://render.janction.jp/changelog.xml). Versions are the PyPI releases of `janction-render`; the hosted service follows the same numbers.

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
