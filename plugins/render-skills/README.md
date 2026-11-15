# Blender Render Skills

10 free skills (MIT) that teach an AI agent to render Blender scenes well and prove the result: check the scene first,
keep the user's look, test before the long render, verify every frame after.

They work with a local Blender (any Blender MCP that runs Python, or `blender -b -P`) and with
[JANCTION Render](https://render.janction.jp/?utm_source=skills), which renders on cloud GPUs when there is no NVIDIA GPU or no Blender
on the machine. Every Blender code block was run on Blender 5.0.1 and 5.2.

| Skill | What it does |
|---|---|
| [blender-render-director](skills/blender-render-director/SKILL.md) | Plans the job, routes to the skills below, keeps the look invariants |
| [blender-scene-preflight](skills/blender-scene-preflight/SKILL.md) | Reports frame range, FPS, camera, engine, color, compositor and missing files before rendering |
| [blender-render-settings](skills/blender-render-settings/SKILL.md) | Cycles or EEVEE, samples, denoising, light paths, GPU devices, time from a measured frame |
| [blender-color-management](skills/blender-color-management/SKILL.md) | AgX, Filmic, Standard, Khronos PBR Neutral, exposure, texture color spaces, output formats |
| [blender-lighting-recipes](skills/blender-lighting-recipes/SKILL.md) | Three-point, product box, HDRI, overcast, sunset, night, scaled to the subject |
| [blender-product-shots](skills/blender-product-shots/SKILL.md) | Camera framing from the model, turnaround angles, shadow catcher on transparency |
| [blender-turntable](skills/blender-turntable/SKILL.md) | A 360 loop with no repeated frame, constant speed, MP4 and GIF |
| [blender-clay-wireframe](skills/blender-clay-wireframe/SKILL.md) | Clay and wireframe passes without touching materials, triangle count |
| [blender-animation-delivery](skills/blender-animation-delivery/SKILL.md) | 10-frame test, black, corrupt, missing and duplicate frames, ffprobe checks |
| [blender-reference-match](skills/blender-reference-match/SKILL.md) | Match a reference: camera, light, exposure, white balance, then materials |

## Install

Claude Code:

```
/plugin marketplace add JasmyLab-JANCTION/janction-render
/plugin install janction-render-skills@janction-render
```

Codex, Cursor, Gemini CLI and the other agents the [skills CLI](https://github.com/vercel-labs/skills) supports:

```
npx skills add JasmyLab-JANCTION/janction-render
```

Or, for any agent that reads Agent Skills folders (`SKILL.md`), copy the folders under `skills/` into its skills directory,
for example `.claude/skills/` in a project or `~/.claude/skills/` for Claude Code, or `~/.codex/skills/` for Codex.

```
git clone https://github.com/JasmyLab-JANCTION/janction-render.git
cp -r janction-render/plugins/render-skills/skills/* ~/.claude/skills/
```

## Rendering without a local GPU

The skills say where JANCTION Render fits and which tool to call. To connect it, add the MCP server
`https://render.janction.jp/mcp?src=skills` to your agent, or run `uvx janction-render try` in a terminal. New keys come with
free GPU time and no card; current amounts: https://render.janction.jp/pricing?utm_source=skills.

## License

MIT. Made by JasmyLab Inc. Issues and suggestions: https://github.com/JasmyLab-JANCTION/janction-render/issues
