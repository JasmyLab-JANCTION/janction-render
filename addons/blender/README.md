# JANCTION Render for Blender

A Blender extension (Blender 4.2 or newer) that renders the open .blend file on
JANCTION cloud GPUs from the Render properties. It needs no local GPU and no
sign-up: a key is created with one click, with 10 free GPU-minutes a day.

What it does:

- Preview: renders up to 4 frames of the scene frame range as one sheet (2x2,
  up to 1280x720, low samples) and shows it in an Image Editor.
- Estimate: asks the server how long the final render would take and whether it
  fits today's free quota.
- Final render: renders the scene frame range as an MP4 or as PNG frames and
  saves the result next to the .blend.

The file is never modified. The add-on saves a copy to a temporary folder,
uploads the copy, and deletes the copy when the job is over.

## Install

From the extension repository (installs and updates without a zip):

1. Edit > Preferences > Get Extensions > the drop-down menu at the top right >
   Repositories > + > Add Remote Repository, URL
   `https://render.janction.jp/extensions/index.json`.
2. JANCTION Render appears in the extension list; press Install. It is enabled
   right away (check under Add-ons if not).

From a zip:

1. Download `https://render.janction.jp/extensions/janction_render-0.1.2.zip` (the GitHub release
   `blender-addon-0.1.0` holds the first version), or build it
   (`python scripts/build_blender_addon.py` in this repository writes it to `dist/`;
   `blender --command extension build --source-dir addons/blender/janction_render --output-dir dist`
   is the official equivalent).
2. In Blender: Edit > Preferences > Get Extensions > the drop-down menu at the top
   right > Install from Disk, and pick the zip.
3. Enable it under Add-ons if it is not enabled already.

The repository index is made with `blender --command extension server-generate --repo-dir=<folder with the zip>`
and served from the service's `data/extensions/` folder.

The panel is in Properties > Render > JANCTION Render.

## The key

The service has no accounts. Press "Get a free key" in the panel or in the
add-on preferences: the add-on calls `POST /v1/keys`, stores the key in the
add-on preferences (shown as a password field) and shows today's remaining free
GPU minutes. The key is saved with your Blender preferences, so it survives
restarts. Anyone with the key can use its quota; treat it like a password. To
start over, clear the field and press the button again.

Each key gets 10 free GPU-minutes per day (20 per network); the counter resets
at 00:00 UTC and the panel shows the minutes left. GPU time beyond that costs
0.1 JPY per GPU-second from prepaid credit (https://render.janction.jp/pricing).
When a render goes past the free time without enough credit, the panel shows
Open top-up page (Stripe Checkout in the browser); pay there and press the button again.

## What gets uploaded

- A copy of the open .blend (saved with compression; relative paths are kept
  as they are so the files below are found).
- Images, fonts and Alembic caches that the file references with a relative
  path (`//textures/wood.png`) and that are inside the .blend folder. They are
  sent under the same relative name, so the server lays them out next to the
  scene exactly as on your disk.
- Packed images need nothing: they travel inside the .blend.

Not uploaded, and reported as warnings in the panel and the Info editor:
absolute paths, files above the .blend folder (`//../`), image sequences and
movies, linked libraries, sounds and volumes, and file names with characters
other than letters, digits, `.`, `_`, `-` (for example Japanese names). Pack
such files (File > External Data > Pack Resources) or rename them.

Uploads and results are deleted 24 hours after last use. Nothing is used for
training. Files run only inside a disposable container on the GPU worker.
Details: https://render.janction.jp/security

Results are written to a `janction_render` folder next to the .blend
(`preview_<date>.png`, `final_<date>.mp4` or `final_<date>/frame_0001.png`...).
An unsaved file uses a temporary folder; the path is shown in the panel.

## Limits

- Preview: up to 4 frames, up to 1280x720, up to 32 samples. The scene's
  resolution and samples are used and clamped.
- Final: up to 240 frames per job and up to 1080p (1920x1080 pixels). Longer
  ranges are cut at 240 frames and larger resolutions are scaled down; the
  panel says so. Samples: the scene's Cycles samples capped at 128, or your own
  number when "Scene samples" is off.
- Engine: Cycles on GPU. The worker opens the file with Blender 5.0 or 5.2.
  The default, "Match this Blender", picks 5.2 when your Blender is 5.1 or
  newer and 5.0 otherwise, so a file is never opened by an older Blender than
  the one that saved it; choose explicitly in the panel or the preferences.
- Environment presets (studio, sunset, overcast, night) replace the world with
  a bundled HDRI; "Scene world" keeps yours.
- Uploads: at most 40 companion files per scene, 128 MB each.

## Troubleshooting

- "No API key": open the preferences (or the panel) and press "Get a free key".
- "cannot reach render.janction.jp": no internet, a proxy, or a firewall. The
  add-on uses Blender's bundled Python and plain HTTPS on port 443.
- "Daily free quota used up; resets at ...": wait for the reset or use another
  key on another network.
- Textures are pink in the result: the image was not sent. Check the warnings
  in the Info editor (Scripting workspace); make paths relative (File >
  External Data > Make Paths Relative) or pack the images.
- The preview does not appear: it is saved in the `janction_render` folder;
  open an Image Editor and the next preview shows there, or press the folder
  button in the panel.
- "Render failed: ...": the message comes from Blender on the worker. Common
  causes are a missing camera, a file from a newer Blender (try 5.2), or a
  script in the file that needs an add-on the worker does not have.
- Nothing happens after pressing Final: the panel asks for confirmation first.
- Reinstalling: Preferences > Get Extensions > Installed > JANCTION Render >
  Remove, then install the new zip.
