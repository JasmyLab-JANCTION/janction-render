# Cursor rule for JANCTION Render

`janction-render.mdc` is a Cursor project rule. It tells the agent when to use JANCTION Render (cloud GPU rendering for Blender over MCP), how to connect, and the preview-first flow.

Install:

1. Copy `janction-render.mdc` into your project's `.cursor/rules/` folder.
2. Add the MCP server to `.cursor/mcp.json`:

```json
{ "mcpServers": { "janction-render": { "url": "https://render.janction.jp/mcp" } } }
```

The rule attaches automatically when you work on `.blend`, `.py`, `.glb`, `.gltf`, `.fbx`, `.usd` or `.obj` files. The first tool call opens a consent page that issues a free API key.

Guide: https://render.janction.jp/cursor-blender
