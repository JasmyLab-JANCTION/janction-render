# janction-render (npm)

Blender scenes and 3D models (GLB, FBX, USD, OBJ, STL) rendered on cloud GPUs from Claude Desktop and other stdio-only MCP clients: product shots, 360-degree turntables, animations and stills. No local GPU or Blender; free to start. One command connects the client to **JANCTION Render**: a preview in seconds with a critic verdict and fix code, then the final frames or an MP4. The same service as the Python package `janction-render` on PyPI and the remote MCP endpoint `https://render.janction.jp/mcp`.

```
npx -y janction-render
```

The first tool call opens a consent page that creates a free key: 100 JPY of GPU time with no card, 400 JPY more after saving a card on a page that charges nothing, then 0.1 JPY per GPU-second (previews stay free up to 2 GPU-minutes a day). Details: https://render.janction.jp/pricing

## Add it to your client

Claude Desktop, Cursor, Windsurf, Cline and other stdio clients (`mcpServers` in the config):

```json
{
  "mcpServers": {
    "janction-render": { "command": "npx", "args": ["-y", "janction-render"] }
  }
}
```

Claude Code:

```
claude mcp add janction-render -- npx -y janction-render
```

Clients that speak Streamable HTTP with OAuth (Claude.ai, ChatGPT, Codex, Cursor) do not need this package: give them `https://render.janction.jp/mcp` directly.

## Options

| | |
|---|---|
| `--key jr_...` | use an API key instead of OAuth (also `JANCTION_RENDER_API_KEY`); the key is passed through a temporary file, never on the command line of the bridge |
| `--url <url>` | another endpoint (default `https://render.janction.jp/mcp?src=npm`) |
| `--local` | run the Python stdio server through `uv` instead of the remote bridge; it sends local `.blend` / 3D files and saves results under `~/janction-render/<job_id>` |
| `-- <args>` | passed to `mcp-remote` (for example `--transport sse-only`) |

## What the tools do

`render_preview` (an image in seconds plus a critic verdict), `render_estimate`, `render_final` (frames or MP4, up to 1,000 frames per instruction run as parts of 240 under one job id; 1080p on free time, 4K on prepaid credit), `render_status`, `render_download`, `scene_info`, `asset_search` (CC0 models, textures and HDRIs from Poly Haven), `billing`, `render_share`. `preset='product' | 'turntable' | 'animation'` fills the camera, light, backdrop, frames and output for that purpose.

Scenes are a `.blend`, a bpy script (Blender 5.0 API) or a 3D file (glTF/GLB, FBX, USD, OBJ, STL, PLY, Alembic). Files are deleted 24 hours after last use and never used for training.

## Links

- Site and guides: https://render.janction.jp
- Agent-readable summary: https://render.janction.jp/llms.txt
- Source: https://github.com/JasmyLab-JANCTION/janction-render (this launcher lives in `npm/`)
- Operated by JasmyLab Inc.
