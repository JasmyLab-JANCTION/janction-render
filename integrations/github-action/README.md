# JANCTION Render GitHub Action

Render a Blender scene, a bpy script or a 3D file (GLB, glTF, FBX, USD, OBJ) on JANCTION Render's cloud GPUs from a
workflow: a preview image on every push, a turntable or an animation MP4 on a release. No Blender or GPU on the runner.

The action runs the `janction-render` command line tool (PyPI), the same API the MCP server uses. It estimates the job
first and stops before anything starts when the job could cost more than `max-cost-yen`; the same cap is sent with the
job, so the service refuses it before any credit is held.

## Use

1. Get an API key: `curl -s -X POST https://render.janction.jp/v1/keys` returns a new `api_key` that starts with free GPU
   time (no sign-up). A key the CLI already uses is in `~/.janction-render.json`.
2. Add it as a repository secret named `JANCTION_RENDER_API_KEY`.
3. Add a workflow:

```yaml
name: render
on:
  push:
    paths: ["scenes/**"]
jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: JasmyLab-JANCTION/janction-render/integrations/github-action@v0.4.41
        id: render
        with:
          api-key: ${{ secrets.JANCTION_RENDER_API_KEY }}
          scene-file: scenes/product.blend
          kind: preview
          frames: "1-24"            # up to 4 frames tiled in one image
          max-cost-yen: 0           # only what the free GPU time covers
      - uses: actions/upload-artifact@v4
        with:
          name: render-preview
          path: render-output
```

A final MP4 on release:

```yaml
      - uses: JasmyLab-JANCTION/janction-render/integrations/github-action@v0.4.41
        with:
          api-key: ${{ secrets.JANCTION_RENDER_API_KEY }}
          scene-file: scenes/turntable.blend
          kind: final
          frames: "1-96"
          width: 1920
          height: 1080
          output: mp4
          max-cost-yen: 200
          timeout-seconds: 1800
```

## Inputs

| input | default | |
|---|---|---|
| `api-key` | (required) | Repository secret with the API key. |
| `scene-file` | (required) | Path to a .blend, a .py bpy script or a 3D file, or an https link. Files a .blend references by relative path are sent with it. |
| `kind` | `preview` | `preview` (up to 4 frames in one image, up to 1280x720) or `final`. |
| `frames` | `1` | Preview: `1`, `1-24` or `1,8,16`. Final: a range such as `1-48` (at most 240 per job). |
| `width`, `height` | `1280`, `720` | Final up to 1920x1080. |
| `samples` | 16 / 128 | Cycles samples per pixel (preview / final). |
| `output` | `auto` | Final: `mp4`, `png`, `exr`, `webm`, `gif` or `webp`. |
| `max-cost-yen` | `100` | The job is refused before it starts if it could cost more (JPY). `0` = free GPU time only. |
| `timeout-seconds` | `900` | Cancels the job after this long (only frames already rendered are charged). |
| `output-dir` | `render-output` | Where the files are written. |
| `allow-fork-pull-requests` | `false` | `pull_request_target` runs from forks are refused unless this is `true`. |
| `cli-version` | pinned | Version of `janction-render` on PyPI. |

Outputs: `job-id`, `files` (JSON array), `gpu-seconds`, `charged-yen`. The job summary shows the same.

## Safety

- The key is masked in the log and passed to the tool through the environment, never on a command line.
- Without a key the action fails; it never creates a key on its own.
- Pull requests from forks do not get secrets on `pull_request`; on `pull_request_target` the action refuses forks unless
  `allow-fork-pull-requests: true`.
- A rerun of the same workflow attempt reuses the job (idempotency key from the run id, the attempt and the scene), so a
  retried step never renders or charges twice. A new attempt ("Re-run jobs") renders again.
- The cap is checked twice: by the estimate before the job is submitted, and by the service when it receives the job.

Pricing and free GPU time: https://render.janction.jp/pricing. Questions: https://render.janction.jp/support.
