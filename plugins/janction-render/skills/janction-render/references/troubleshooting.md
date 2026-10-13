# Troubleshooting JANCTION Render

Every error has `error` (a short name), `detail` (a sentence), `code`, `retryable` and `recommended_action`. A failed job
also has `failure` with `code`, `category`, `reason`, `recommended_action` (a sentence) and `fix_by`
(`agent` = fix the script or the arguments, `user` = needs the user's input, `service` = wait or resubmit).

## Connection

- Tools missing, or `AUTH_REQUIRED`: the server is not authenticated. Claude Code: `/mcp` -> janction-render ->
  Authenticate. Codex: `codex mcp login janction-render`. Gemini CLI: `/mcp auth janction-render`. Claude.ai and ChatGPT:
  open the connector settings and connect again. Connecting creates a free key; no account or card is needed.
- Codex stops with `MCP tool call requires approval, but approval policy is never`: Codex asks before each MCP tool
  call and `codex exec` cannot ask, so the call never reaches the service. Tell the user to allow it when Codex asks, or to
  approve the read, preview and estimate tools one by one in `~/.codex/config.toml`, under the server entry that has its
  `url` (https://render.janction.jp/codex-blender#run-without-prompts). Leave `render_final` asking.
- The browser page says "unknown app": the app's redirect address is not one the service knows. Use the official app or
  pass an API key as `Authorization: Bearer <key>` instead.
- Terminal check: `uvx janction-render doctor` reports the service, the key, the credit and the AI apps on the machine.
- Antigravity CLI shows janction-render as Disabled (untrusted): it stops MCP servers in folders it does not trust. Trust the
  folder (the first-run prompt, or `trustedWorkspaces` in its settings) and start it again.

## Money

- `INSUFFICIENT_CREDIT` (402): the job goes past the free GPU time and the credit is short. Relay `tell_user`, show
  `checkout_url`; the user pays in the browser (Stripe). Then call `billing` and submit the same job again. Never enter
  payment details yourself.
- `COST_LIMIT_EXCEEDED` (403): above the spending cap of the key (`scope: job` or `day`) or the `max_yen` sent with the job
  (`scope: request`). Ask the user. Offer fewer frames, a lower resolution, fewer samples or `engine="eevee"`.
- `QUOTA_EXCEEDED` (429): the free time for today is used up; `resets_at` says when it comes back, `suggested` says which
  frames still fit today.

## Input

- `JOB_TOO_LARGE`: over 3,000 frames in one instruction (longer finals are split into parts of 240 under one job id
  automatically), over 1920x1080 on free time (up to 4K on prepaid credit) or over 10 GPU-hours. Split the frame range.
- `SCRIPT_BLOCKED`: the script uses something the sandbox refuses (subprocesses, sockets, network imports such as urllib or
  requests, absolute paths). Keep the script to building the scene; pass web files in `asset_urls`.
- `MISSING_ASSET`: a texture, `.bin` or `.mtl` is missing or points outside the upload. Pass it in `asset_urls` (https) or
  pack it into the .blend (File > External Data > Pack Resources).
- `UNSUPPORTED_VERSION`: the script uses an API that changed in Blender 5.x (`mat.use_nodes`, `action.fcurves`), or the
  importer failed on a file. Rewrite the line for 5.0, or try `blender="5.2"` for imports.
- `INVALID_SCENE`: no camera, a syntax error, an unreadable file. Read `failure.reason` and `log_tail`, fix, preview again.

## Waiting

- `WORKERS_UNAVAILABLE`, or `eta.human` says the GPU is lent out: the job waits in the queue and starts when the GPU is back.
  Tell the user the expected wait from `eta.gate`; do not poll in a loop.
- `JOB_TIMEOUT`: a chunk ran past the limit. Lower samples or resolution, or render fewer frames per job.
- `RATE_LIMITED`: wait `retry_after_s` seconds (also in the `Retry-After` header).

## Retries

- Retry only when `retryable` is true, at most twice.
- A final render that timed out on your side may still be running: check `render_status` or the job list before submitting
  again. Over the HTTP API or the CLI, send an `Idempotency-Key` so a resubmission returns the first job instead of
  rendering and charging twice.
