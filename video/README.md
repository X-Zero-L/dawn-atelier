# Dawn Atelier video

A 54-second showcase for 黎明工坊, the Windows desktop save editor for 《黎明门前的吹笛人》. Screens show desktop launch, synthetic demonstration data, progression preparation, and staged editor previews.

## Reproduce

Requires Node.js 22 or newer. All Remotion packages are pinned to **4.0.529**; React and React DOM to **19.2.3**.

```sh
npm ci
npm run assets
npm run studio
npm run render
npm run poster
```

`npm run assets` reads the screenshot list from `../scripts/media-config.json`, requires all 20 current screenshots in `../docs/images/`, copies them into ignored `public/`, and records their dimensions and SHA-256 hashes. It also checks the bundled font against its recorded upstream hash. The render, poster and studio commands prepare the assets automatically. Missing inputs fail before any screenshots are copied.

Required inputs are listed in `scripts/media-config.json`: desktop launch/preparation, the workbench gallery, alchemy resources and unlock conditions, workshop growth, and the corresponding change previews. The two desktop screenshots are 1280 × 900 and appear as complete viewports.

The render is **1920 × 1080**, **30 fps**, **1620 frames**, H.264, CRF 18, YUV 4:2:0. Output goes to ignored `out/`. `src/timeline.json` defines the composition duration, chapter timing, poster frame, and representative sample frames. `src/index.jsx` and the composition consume that same file. A different destination can be passed directly:

```sh
npx remotion render src/index.jsx DawnAtelier path/to/demo.mp4 --codec=h264 --crf=18 --pixel-format=yuv420p
npx remotion still src/index.jsx DawnAtelier path/to/poster.png --frame=225
```

The video uses deterministic native React/SVG motion and makes no network requests while rendering. It is silent, so it works in README previews and without audio playback.

For an optional 27-second, 640px-wide GIF teaser, install FFmpeg and run:

```sh
ffmpeg -i out/dawn-atelier-demo.mp4 -filter_complex "[0:v]setpts=0.5*PTS,fps=5,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" -an -loop 0 out/dawn-atelier-demo.gif
```

## Local font coverage

`src/fonts/DawnSans.ttf` is the complete upstream Noto Sans SC variable font, so new Chinese captions do not need a manual subset rebuild. The official source URL and SHA-256 are recorded in `src/fonts/font.json`; its SIL Open Font License is in `src/fonts/OFL.txt`. The 17.8 MB font is bundled locally and is never downloaded at render time.

## Chapters

| Time | View |
| --- | --- |
| 0:00 | Product overview |
| 0:04.5 | Windows one-click package and automatic desktop preparation |
| 0:10.5 | Ten presets and 19 configurable operations |
| 0:15.5 | Super supply: copper, iron, and gold ingots |
| 0:22.5 | Alchemical sediment and quick targets |
| 0:28 | Inventory |
| 0:31.5 | Relationships |
| 0:34.5 | Tool upgrades |
| 0:37.5 | Workshop and alchemy condition preparation |
| 0:43.5 | Change preview and backups |
| 0:49.5 | Closing title |

Representative still frames: intro **84**, desktop **210**, preparing **285**, supply **540**, sediment **735**, workshop **1200**, alchemy preparation **1270**, final review **1410**, outro **1560**. The poster uses **225**. These are also available under `sampleFrames` in the timeline metadata.

The asset helper accepts `--source <directory>` for a different local directory containing the same 20 filenames. Release generation should use the root media pipeline so every screenshot comes from the current fixed demo fixture before rendering. The current complete list is defined in `scripts/media-config.json`.
