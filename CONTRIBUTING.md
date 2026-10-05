# Contributing

Thanks for looking at JANCTION Render. This repository holds the client side: the stdio MCP server, the CLI, the HTTP client, samples, the Claude Code plugin, the Blender add-on and the Maya / Houdini / Cinema 4D tools. The GPU service itself (the API server and the workers) is not in this repository.

## Reporting problems

- Bugs and questions: open an issue with the template. Include the version (`pip show janction-render` or the `v` in the page footer), the client you used (Claude, ChatGPT, Codex, Cursor...) and the job id if you have one.
- Security: see [SECURITY.md](SECURITY.md); do not file exploitable details publicly.

## Pull requests

Small, focused changes are welcome: docs, samples, client fixes, integrations for other DCC tools. For anything that changes a tool name, a tool signature or the wire format of the API, open an issue first; those surfaces are listed in registries and reviewed by AI client directories, so they change rarely and deliberately.

Before opening a PR:

1. `pip install -e .[dev]` (or at least `pip install -e .`), Python 3.11+.
2. Run `python -m pytest -q` for the client tests in this repository.
3. Keep the English wording of user-facing text consistent with the site (https://render.janction.jp/llms.txt is the reference).

By contributing you agree that your contribution is licensed under the MIT license (the Blender add-on under `addons/blender/` is GPL-3.0-or-later, as Blender requires).

## Code of conduct

Be direct and kind. Reports about conduct go to kato@jasmylab.com.
