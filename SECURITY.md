# Security policy

JANCTION Render runs user-supplied Blender files and bpy scripts on GPUs, so we treat security reports as the highest-priority issue type.

## Reporting a vulnerability

Email **security@jasmylab.com** (or kato@jasmylab.com) with the steps to reproduce, the affected endpoint or tool, and the impact you observed. Please do not open a public issue for anything exploitable. We acknowledge reports within 2 business days and tell you when a fix is deployed.

Please test only against resources you control: your own API keys, your own uploads. Do not attempt to read other users' files, exhaust the shared GPU, or mine on it. If you need a dedicated key for testing with higher limits, ask and we will issue one.

## What is in scope

- https://render.janction.jp (HTTP API under /v1, the remote MCP endpoint /mcp, the OAuth endpoints, the web pages)
- The published packages: `janction-render` on PyPI, the Claude Code plugin, the Blender add-on and the DCC tools in this repository

## What we already do

The current isolation model, rate limits, data retention and the summary of the external review (2026-10-01 and 10-02) are described at https://render.janction.jp/security . Known remaining item before paid keys: a second isolation layer (AppArmor or gVisor) for the render containers.

## Supported versions

Only the latest release on PyPI and the live service are supported. Security fixes are shipped as a new version and noted in https://render.janction.jp/changelog .
