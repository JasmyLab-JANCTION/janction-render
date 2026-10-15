# n8n-nodes-janction-render

An [n8n](https://n8n.io) community node for [JANCTION Render](https://render.janction.jp): render Blender scenes and 3D models (GLB, glTF, FBX, USD, OBJ, STL, .blend, or a bpy script) on cloud GPUs. Turn a product model into studio shots or a 360-degree turntable MP4 inside a workflow, with no local Blender or GPU.

## Install

In n8n: **Settings > Community Nodes > Install**, then enter `n8n-nodes-janction-render`.

## Credentials

Create a key at https://render.janction.jp/start (a new key comes with free GPU time) and paste it into **JANCTION Render API** (`jr_...`, sent as `X-API-Key`).

## Operations

- **Render**: start a preview (up to 4 frames tiled in one image, seconds) or a final render. The scene is a file URL, a bpy script or a `scene_id` from an earlier job. Presets: `product` (4 studio shots), `turntable` (one full turn as MP4), `animation`. Returns `job_id`.
- **Estimate**: GPU seconds, wall time, queue wait and the cost in JPY before rendering.
- **Get Job**: status, ETA and, when done, the image or MP4 links (no key needed, about 24 hours).

A typical workflow: trigger (new product in your shop) > **Render** (File URL = the GLB, Preset = Product Shots, Kind = Final) > **Wait** 60 s > **Get Job** > loop until `status` is `done` > send the links.

## Pricing

Free GPU time for a new key, then 0.1 JPY per GPU-second from prepaid credit. Current numbers: https://render.janction.jp/pricing

## License

MIT. Operated by JasmyLab Inc. (Tokyo, Japan).
