# Dawn Atelier video

A 32-second product showcase made with Remotion. Screens show synthetic demonstration data and staged editor previews.

## Reproduce

Requires Node.js 20 or newer. All Remotion packages are pinned to **4.0.529**; React and React DOM to **19.2.3**.

```sh
npm ci
npm run assets
npm run studio
npm run render
npm run poster
```

`npm run assets` copies the seven released screenshots from `../docs/images/` into ignored `public/` and records their SHA-256 hashes. Run it again after changing the screenshots. The source images are `overview.png`, `presets.png`, `inventory.png`, `relationships.png`, `tools.png`, `preview.png`, and `mobile.png`.

The render is **1920 × 1080**, **30 fps**, **960 frames**, H.264, CRF 18, YUV 4:2:0. Output goes to ignored `out/`. A different destination can be passed directly:

```sh
npx remotion render src/index.jsx DawnAtelier path/to/demo.mp4 --codec=h264 --crf=18 --pixel-format=yuv420p
npx remotion still src/index.jsx DawnAtelier path/to/poster.png --frame=84
```

The video uses deterministic native React/SVG motion, no network requests while rendering, and a bundled subset of Noto Sans SC. The font retains its SIL Open Font License in `src/fonts/OFL.txt`. The video is silent, so it works in README previews and without audio playback.

For an optional 16-second, 640px-wide GIF teaser, install FFmpeg and run:

```sh
ffmpeg -i out/dawn-atelier-demo.mp4 -filter_complex "[0:v]setpts=0.5*PTS,fps=5,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" -an -loop 0 out/dawn-atelier-demo.gif
```

The bundled font subset covers the current captions. New Chinese characters need to be included when updating the font subset.

## Chapters

| Time | View |
| --- | --- |
| 0:00 | Product overview |
| 0:04.5 | Presets |
| 0:10 | Inventory |
| 0:14.5 | Relationships |
| 0:18.5 | Tool upgrades |
| 0:23 | Change preview and backups |
| 0:28.5 | Closing title |

Screenshot assets are never fetched from the network. For drafting before final screenshots exist, `scripts/prepare-assets.mjs` also accepts `--draft --source <local-reference-directory>`; release renders must use the default final screenshots.
