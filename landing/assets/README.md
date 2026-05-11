# Landing-page assets

`index.html` references these files. Drop the listed PNGs in this directory and
the page will pick them up automatically — no build step.

## Logos (already in repo)

| File                          | Used for           | Notes                                            |
| ----------------------------- | ------------------ | ------------------------------------------------ |
| `bodhiorchard-logo.png`       | Hero               | Square PNG, transparent bg, copied from frontend |
| `bodhiorchard-logo-sm.png`    | Favicon            | 32×32 PNG, used as `<link rel="icon">`           |

## Screenshots (TODO — placeholders ship by default)

The HTML currently renders CSS-gradient placeholder tiles instead of these files
so the page never looks broken before they land. When you have real screenshots,
either:

- save them with the exact filenames below and replace the `.shot` `<div>`s with
  `<img>` tags pointing at `assets/...`, **or**
- keep the gradient placeholders for marketing reasons and just drop the files
  here for future use.

| Filename                      | Suggested size      | What it should show                      |
| ----------------------------- | ------------------- | ---------------------------------------- |
| `screenshot-tree.png`         | 1600 × 1200 (4:3)   | Living Tree dashboard, mid-rotation      |
| `screenshot-bud-board.png`    | 1600 × 1200 (4:3)   | BUD board with lanes populated           |
| `screenshot-slack-triage.png` | 1600 × 1200 (4:3)   | Slack thread mid-Triage-agent interview  |

## Demo video

The hero's "Watch the demo" CTA anchors to `#demo`, which currently shows a
gradient placeholder. When the real video is ready, replace the `.video-frame`
`<div>` in `index.html` with an embed iframe (YouTube/Loom) — keep the
`aspect-ratio: 16/9` CSS so the layout doesn't shift.
