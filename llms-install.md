# Installing JANCTION Render (for AI agents and installers such as Cline)

JANCTION Render is a cloud GPU render farm for Blender that AI agents call as an MCP server or HTTP API. No local Blender or GPU is needed. Free beta: 10 GPU-minutes per key per day; a final render is up to 240 frames at 1080p.

## Option A: remote MCP (nothing to install)

Add a Streamable HTTP MCP server with this URL:

    https://render.janction.jp/mcp

Authentication: OAuth 2.1 with dynamic client registration (the connect page creates a free API key), or send an API key as `Authorization: Bearer jr_...`. A key is issued with one request: `POST https://render.janction.jp/v1/keys` with a JSON body `{"label": "my-agent"}`.

Cline / Cursor / Windsurf style config:

    {
      "mcpServers": {
        "janction-render": {
          "type": "streamableHttp",
          "url": "https://render.janction.jp/mcp"
        }
      }
    }

## Option B: stdio MCP (sends local files, Python 3.11+)

    pip install janction-render

or, without a global install:

    uvx --from janction-render janction-render-mcp

Config:

    {
      "mcpServers": {
        "janction-render": {
          "command": "uvx",
          "args": ["--from", "janction-render", "janction-render-mcp"],
          "env": { "JANCTION_RENDER_SERVER": "https://render.janction.jp" }
        }
      }
    }

A temporary API key is created on first use and cached in `~/.janction-render.json`. Set `JANCTION_RENDER_API_KEY` to pin one.

## Verify

Call `render_info` (no GPU time) and then `render_preview` with the sample scene:

    render_preview(scene_url="https://render.janction.jp/samples/cube_scene.py")

A tiled 4-frame preview image comes back within seconds. Tools: scene_info, render_preview, render_estimate, render_final, render_status, render_download, render_cancel, render_share, render_unshare, asset_search, billing, render_info.

Docs: https://render.janction.jp/llms.txt (agents) and https://render.janction.jp/blender-render-api (humans). Operated by JasmyLab Inc.
