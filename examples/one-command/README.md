# One command each: real outputs

These files are what the commands below produced on JANCTION Render's production GPU (NVIDIA RTX PRO 6000 Blackwell)
on 2026-10-10, scaled down for the README (the shots are 1920x1080 PNGs and the videos are MP4s; the GIFs here are
480 px previews made from them).

The model is [WaterBottle](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/WaterBottle) from
Khronos's glTF sample assets, dedicated to the public domain (CC0 1.0) by Microsoft. The logo animation is
[`samples/ex12_logo_ring_spin.py`](../../samples/ex12_logo_ring_spin.py) (also at https://render.janction.jp/samples/ex12_logo_ring_spin.py).

| File | Command | GPU time | Price at 0.1 JPY per GPU-second |
|---|---|---|---|
| `product-shots.png` | `uvx janction-render shots https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/Models/WaterBottle/glTF-Binary/WaterBottle.glb` | 13.9 s | about 1.4 JPY |
| `turntable.gif` | `uvx janction-render turntable https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/Models/WaterBottle/glTF-Binary/WaterBottle.glb` | 85.2 s | about 8.5 JPY |
| `anim.gif` | `uvx janction-render render https://render.janction.jp/samples/ex12_logo_ring_spin.py --frames 1-48 --size 1280x720 --engine eevee --output mp4 --wait` | 54.1 s | about 5.4 JPY |

`uvx` needs [uv](https://docs.astral.sh/uv/); `pip install janction-render` and drop the `uvx` works too. The first run
creates a free key (each new key starts with a 500 JPY welcome credit, which covers all three). The CLI accepts a local
path or an https link; links to file pages on GitHub and Hugging Face are turned into raw links.

The shots and the turntable are fixed-price outcomes (`POST /v1/outcomes/product-shot` and `/turntable`): the price
ceiling is shown before anything runs and only the GPU time actually used is charged. They frame the object at its real
size and use a plain backdrop lit by the studio HDRI (`environment_visible=true` shows the HDRI photo instead,
`--transparent` gives PNGs with alpha).
