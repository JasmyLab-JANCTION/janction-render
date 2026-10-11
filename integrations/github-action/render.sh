#!/usr/bin/env bash
# JANCTION Render GitHub Action: a preview or a final render through the janction-render CLI
# (the same API as the MCP server; no separate logic here). Inputs arrive as JR_IN_* (action.yml).
#   1. refuse without a key, and for pull_request_target from forks unless allowed
#   2. estimate first and stop before anything starts when it could cost more than max-cost-yen
#   3. render with the same cap sent to the service (it refuses the job before holding any credit)
#   4. on timeout, cancel the job; write the files, the outputs and the job summary
set -euo pipefail

fail() {
  echo "::error title=JANCTION Render::$1"
  exit "${2:-1}"
}

PY=""
for cand in python3 python; do   # Windows has a python3 stub that only opens the Store: take the first one that runs
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys; sys.exit(sys.version_info < (3, 10))" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
[ -n "$PY" ] || fail "Python 3.10 or later is not available on this runner (actions/setup-python adds it)"

# ---- 1. key and forks
[ -n "${JR_IN_API_KEY:-}" ] || fail "api-key is empty. Add a repository secret (Settings > Secrets and variables > Actions) and pass it as api-key. Pull requests from forks do not receive secrets; this action never creates a key by itself."
echo "::add-mask::${JR_IN_API_KEY}"

if [ "${GITHUB_EVENT_NAME:-}" = "pull_request_target" ] && [ "${JR_IN_ALLOW_FORKS:-false}" != "true" ] && [ -f "${GITHUB_EVENT_PATH:-}" ]; then
  fork="$("$PY" -c 'import json, sys
e = json.load(open(sys.argv[1], encoding="utf-8")); pr = e.get("pull_request") or {}
name = lambda side: ((pr.get(side) or {}).get("repo") or {}).get("full_name")
print("yes" if name("head") != name("base") else "no")' "$GITHUB_EVENT_PATH")"
  [ "$fork" = "no" ] || fail "refusing to render for a pull request from a fork (it would spend your credit). Set allow-fork-pull-requests: true to allow it."
fi

# ---- inputs
case "${JR_IN_KIND}" in preview|final) ;; *) fail "kind must be preview or final (got '${JR_IN_KIND}')" ;; esac
for v in JR_IN_MAX_YEN JR_IN_TIMEOUT JR_IN_WIDTH JR_IN_HEIGHT; do
  [[ "${!v}" =~ ^[0-9]+$ ]] || fail "${v#JR_IN_} must be a whole number (got '${!v}')"
done
[ -z "${JR_IN_SAMPLES}" ] || [[ "${JR_IN_SAMPLES}" =~ ^[0-9]+$ ]] || fail "samples must be a whole number"
[[ "${JR_IN_FRAMES}" =~ ^[0-9][0-9,-]*$ ]] || fail "frames must look like 1, 1-48 or 1,8,16"
if [[ "${JR_IN_SCENE}" != https://* ]] && [ ! -f "${JR_IN_SCENE}" ]; then
  fail "scene-file not found: ${JR_IN_SCENE}"
fi
SAMPLES="${JR_IN_SAMPLES:-}"
[ -n "$SAMPLES" ] || { [ "${JR_IN_KIND}" = preview ] && SAMPLES=16 || SAMPLES=128; }
SIZE="${JR_IN_WIDTH}x${JR_IN_HEIGHT}"
OUT="${JR_IN_OUT_DIR:-render-output}"

# ---- the CLI, pinned, in its own environment (system Python on hosted runners refuses pip installs)
WORK="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/janction-render-action"
mkdir -p "$WORK"
VENV="$WORK/venv"
if [ ! -d "$VENV" ]; then
  "$PY" -m venv "$VENV" >/dev/null || fail "could not create a Python virtual environment"
fi
BIN="$VENV/bin"
[ -d "$VENV/Scripts" ] && BIN="$VENV/Scripts"
SPEC="${JANCTION_RENDER_ACTION_PIP_SPEC:-janction-render==${JR_IN_CLI_VERSION}}"   # the override is for testing this action
"$BIN/python" -m pip install --disable-pip-version-check --quiet "$SPEC" || fail "could not install $SPEC"
export JANCTION_RENDER_API_KEY="${JR_IN_API_KEY}"
export JANCTION_RENDER_SERVER="${JR_IN_SERVER}"
export JANCTION_RENDER_CLIENT="${JANCTION_RENDER_CLIENT:-github-action}"
jr() { "$BIN/python" -m janction_render.cli "$@"; }
field() { "$BIN/python" -c 'import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
for k in sys.argv[2].split("."):
    d = d.get(k) if isinstance(d, dict) else None
print("" if d is None else (json.dumps(d) if isinstance(d, (dict, list)) else d))' "$@"; }

# ---- 2. estimate (no GPU used)
est_args=(estimate "${JR_IN_SCENE}" --frames "${JR_IN_FRAMES}" --size "$SIZE" --samples "$SAMPLES" --max-yen "${JR_IN_MAX_YEN}")
[ "${JR_IN_KIND}" = preview ] && est_args+=(--preview)
set +e
jr "${est_args[@]}" > "$WORK/estimate.json"
rc=$?
set -e
[ $rc -ne 5 ] || fail "this ${JR_IN_KIND} could cost more than max-cost-yen (${JR_IN_MAX_YEN} JPY); nothing was rendered. Raise max-cost-yen, or render fewer frames or a lower resolution." 5
[ $rc -eq 0 ] || fail "the estimate failed (exit $rc); see the log above"
SCENE_ID="$(field "$WORK/estimate.json" scene_id)"

# ---- 3. render with the same cap
if [ "${JR_IN_KIND}" = preview ]; then
  run_args=(preview --scene-id "$SCENE_ID" --frames "${JR_IN_FRAMES}" --size "$SIZE" --samples "$SAMPLES")
else
  # 同じ実行（run_id・attempt・job）からの再送は同じ仕事を返す（二重に描かない・引かない）
  idem="gh.${GITHUB_RUN_ID:-local}.${GITHUB_RUN_ATTEMPT:-1}.${GITHUB_JOB:-job}.${SCENE_ID}.${JR_IN_FRAMES//,/_}"
  run_args=(render --scene-id "$SCENE_ID" --frames "${JR_IN_FRAMES}" --size "$SIZE" --samples "$SAMPLES"
            --output "${JR_IN_OUTPUT}" --idempotency-key "${idem:0:128}" --wait)
fi
set +e
jr "${run_args[@]}" --max-yen "${JR_IN_MAX_YEN}" --out "$OUT" --timeout "${JR_IN_TIMEOUT}" > "$WORK/result.json"
rc=$?
set -e
JOB_ID="$(field "$WORK/result.json" job_id 2>/dev/null || true)"
if [ $rc -ne 0 ]; then
  status="$(field "$WORK/result.json" status 2>/dev/null || true)"
  if [ -n "$JOB_ID" ] && [ -n "$status" ] && [ "$status" != done ] && [ "$status" != failed ] && [ "$status" != canceled ]; then
    jr cancel "$JOB_ID" >/dev/null 2>&1 || true
    fail "job $JOB_ID did not finish within ${JR_IN_TIMEOUT} s and was canceled (only frames already rendered are charged)"
  fi
  error="$(field "$WORK/result.json" error 2>/dev/null || true)"
  fail "the ${JR_IN_KIND} failed${JOB_ID:+ (job $JOB_ID)}: ${error:-exit $rc}"
fi

# ---- 4. outputs and summary
jr status "$JOB_ID" > "$WORK/job.json"
FILES="$(field "$WORK/result.json" files)"
GPU="$(field "$WORK/job.json" gpu_seconds)"
YEN="$(field "$WORK/job.json" cost.charged_yen)"
{
  echo "job-id=$JOB_ID"
  echo "files=$FILES"
  echo "gpu-seconds=$GPU"
  echo "charged-yen=${YEN:-0}"
} >> "${GITHUB_OUTPUT:-/dev/null}"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### JANCTION Render: ${JR_IN_KIND}"
    echo
    echo "| | |"
    echo "|---|---|"
    echo "| scene | \`${JR_IN_SCENE}\` |"
    echo "| frames | ${JR_IN_FRAMES} at ${SIZE}, ${SAMPLES} samples |"
    echo "| job | \`${JOB_ID}\` |"
    echo "| GPU seconds | ${GPU} |"
    echo "| charged | ${YEN:-0} JPY (cap ${JR_IN_MAX_YEN} JPY) |"
    echo "| files | ${OUT}/ |"
    echo
    echo "Upload \`${OUT}\` with actions/upload-artifact to keep the files."
  } >> "$GITHUB_STEP_SUMMARY"
fi
echo "done: job ${JOB_ID}, ${GPU} GPU seconds, ${YEN:-0} JPY -> ${OUT}/"
