# Changelog

The live, per-version list is at https://render.janction.jp/changelog (Atom: https://render.janction.jp/changelog.xml). Versions are the PyPI releases of `janction-render`; the hosted service follows the same numbers.

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
- **Retention as published.** Client IPs are cleared from the database after 90 days (`JR_IP_RETENTION_DAYS`); Blender's console tail is deleted with the job; an unshared page drops its script and prompt; share media is cached for 1 hour instead of 24; the privacy page describes what the logs keep.
- **Security.** `scene_url` / `asset_urls` refuse credentials in the URL; asset downloads stream to disk instead of buffering in memory; glTF null-fixing skips files over `JR_GLTF_FIX_MAX_MB` and survives deeply nested JSON; `.usdz` archives are checked for entry count and compression ratio; webhook (`notify_url`) log lines carry no query or credentials; `JR_SANDBOX_REQUIRED=1` makes the worker fail a job instead of falling back from gVisor to runc.
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

- Getting ready to turn on the card model (a new key gets 100 JPY of free GPU time, and saving a card on a Stripe page that charges nothing adds 400 JPY more, once per card): keys made before the switch keep their welcome credit as it was (JR_WELCOME_CARD_SINCE), the card bonus lasts 14 days from when it is added, and it is not limited by the per-network daily cap.
- The page after saving a card says what happened: free GPU time added, or why not (prepaid cards and cards already used do not qualify, and such a card is not kept). If the card cannot be confirmed yet, nothing is charged and the free time is added later by a billing call or the webhook retry.
- While the card model is on, pages, guides, llms.txt and Markdown describe the welcome credit as up to 500 JPY, with the 100 JPY and 400 JPY split; the changelog keeps its history.

## 0.4.48 (2026-10-12)

- The public wording follows the welcome model: under JR_WELCOME_MODEL=card, the one-line definition (facts.json, /facts, llms.txt), the pricing sentence, the pricing page, /v1/pricing (welcome_credit.card_bonus) and the JSON-LD offer state the cardless amount and the card bonus; under the default network model every text is unchanged.

## 0.4.47 (2026-10-12)

- A second welcome model, off by default (JR_WELCOME_MODEL=card): a new key gets 100 JPY of free GPU time once per network, and saving a card on a Stripe page that charges nothing adds 400 JPY more, once per card (prepaid cards do not qualify). The card is asked for only when the 100 JPY is used up: the 402, /v1/me, the MCP billing reply and /start then carry card_offer with the amount and the fact that nothing is charged. JR_WELCOME_MODEL=network keeps today's 500 JPY per new key. The morning report names the model and the day's new keys, finished renders, paying keys and card registrations, so the two can be compared.
- The dollar figure names its source (JR_USD_JPY_SOURCE, for example an ECB reference rate) and the date it was checked.

## 0.4.46 (2026-10-12)

- A final longer than 240 frames is no longer refused: the service splits it into parts of 240 frames under one job id (b_...), and GET /v1/jobs/{id}, DELETE and the MCP render_status / render_download work on that id; each part is charged on its own GPU seconds and comes back as its own file (part-01_output.mp4, ...). One instruction takes up to 1,000 frames (JR_MAX_FRAMES_PER_INSTRUCTION).
- A dollar figure for reference, when the operator sets JR_USD_JPY and JR_USD_JPY_CHECKED: /v1/me (balance), /v1/estimate (cost), /v1/pricing, the pricing page and the MCP billing reply show the amount in USD next to the yen, marked indicative; charges stay in JPY.

## 0.4.45 (2026-10-12)

- The BlendSwap comparison page is rebuilt on BlendSwap's own page as checked on 2026-10-11 (the price per GPU-hour and the Studio plan, rounding up and the two-credit minimum per job, L40S workers, 250 frames, 500 MB uploads, the bundled Blender versions, no free tier), with what ten previews and one finished scene cost here, and without the blocks it shared with other guides. It also says what we do not claim: no speed comparison between GPUs.
- The number of GPUs available right now, counted the same way as /v1/health, appears on the comparison page and the pricing page and updates itself when GPUs are added; a GPU on standby, shared with other work, is counted separately.
- Jobs charged from prepaid credit may render up to 4K (3840x2160); jobs covered by free time stay at 1080p. One job may use at most 10 GPU-hours, checked on the estimate before anything is held (JR_PAID_MAX_PIXELS, JR_MAX_JOB_GPU_SECONDS).
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

- A browser page, /start, renders your own file without a connector, a CLI or a key you have to manage: choose a .blend, a 3D file or paste the bpy script an AI wrote; the scene is read first (missing files, cameras, frame range), the quote says whether the free GPU time covers it, the preview runs with max_yen 0 so nothing can be charged, and the result page offers the next step (change the light, four angles, a turntable, the animation as MP4, a high-quality still, the same settings on another file, a public page) with its price or 'no payment' before you press. Reloading returns to the last render. JR_START_PAGE=0 turns the page off without touching MCP, CLI or API.
- The guides open /start in the matching state (a GLB-to-MP4 page starts in turntable mode, an animation page in video mode, an AI page with the paste box), and the client guides carry the route for an AI without a connector: a prompt that makes it write the bpy script, which you paste at /start. The home page leads with 'No high-end GPU? Turn your 3D into images and video' and the two buttons.
- Estimates carry the breakdown a person decides with: covered_by_free_yen, from_credit_yen, max_charge_yen (the ceiling) and pricing_version; facts.json and /v1/pricing carry the same pricing version.
- Every scene records where it came from (upload, link, /upload drop, pasted script, or an operator sample) and jobs report input.own. The scorecard and the weekly metrics count 'first success with the user's own input', demo-only keys and repeat use on another day, and split money into credit consumed and free time covered.
- A daily budget for free GPU time across the service (JR_FREE_DAILY_BUDGET_YEN; off by default): when it is reached, new free jobs wait for the next day with a clear 429 while paid jobs run. Granted welcome credit is not reduced.
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
- Service: a second isolation layer (gVisor) added to the render sandbox.
- Service: when Blender 5.0's importer fails on an uploaded 3D file and the job did not ask for a Blender version, the same chunk is retried once with Blender 5.2 (`params.blender_auto` says so); if 5.2 fails too, the failure says to re-export the file. Importer crashes are reported as `IMPORTER_ERROR` instead of a script error.
- Service: a refund made on Stripe (`charge.refunded`) takes the refunded amount back out of the key's credit once, matched to the payment by its PaymentIntent; credit already spent on renders cannot be taken back and is reported to the operator. `tools/stripe_check.py --sync-events` adds the refund event to an existing webhook.
- Service: `billing()` on the remote MCP checks the key's open checkouts with Stripe and credits paid ones, so a payment counts even when the webhook is late; job results carry `cost.free_gpu_seconds` (the part covered by the free daily time); the payment page tells chat users (Claude, ChatGPT) to go back to their agent; the operator gets a Slack line per credited payment and a billing line in the daily report.
- Blender add-on 0.1.2 (`/extensions/index.json`): when a render goes past today's free GPU time without enough credit, the panel says how much credit it needs and shows an **Open top-up page** button (Stripe Checkout in the browser); after paying, press the same button again. The add-on's own version string (User-Agent) now matches the manifest.

## 0.4.24 (2026-10-08)

- The README (PyPI, GitHub, Glama), the Claude Code plugin description, the Cursor rule, the Blender add-on and the Maya / Houdini / Cinema 4D submit tools describe the free daily GPU time (10 GPU-minutes per key) and the price beyond it (0.1 JPY per GPU-second); the `billing()` row of the tools table was still "free-beta quota".
- Blender add-on 0.1.1 (`/extensions/index.json`, `janction_render-0.1.1.zip`): wording only — tagline, key tooltip, final-render tooltip and the per-job limit notes.
- `tests/test_live_wording.py` also reads README.en.md, the plugin, the add-on and the DCC tools.

## 0.4.23 (2026-10-08)

- Paid use started on 2026-10-08 (`JR_BILLING_MODE=live`). Each key keeps its free GPU-minutes per day (10, or 20 per network): a job that fits the time left today is free, and a job that goes past it reserves and is charged only for the GPU seconds beyond the free time, at 0.1 JPY per GPU-second from prepaid credit (Stripe Checkout, from 500 JPY). A 402 `payment_required` says how much of the job the free time covers (`free_gpu_seconds_left_today`, `estimated_gpu_seconds`).
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
