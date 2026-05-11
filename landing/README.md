# Bodhiorchard landing page

A single-file, dependency-free landing page for **bodhiorchard.com** (or
wherever the marketing site eventually lives). No build step — open
`index.html` in a browser, or serve `/landing/` with any static host.

## Files

| Path                 | Purpose                                               |
| -------------------- | ----------------------------------------------------- |
| `index.html`         | The full page — inline CSS + inline `<script>`        |
| `assets/`            | Logos + screenshot drop zone (see `assets/README.md`) |

## Maintaining it

The page is intentionally hand-rolled HTML — < 400 lines, no frameworks, no
bundler. Edit `index.html` directly. The hot paths:

- **Tagline** is in the `.hero .tagline` paragraph. Two-liner sub-tagline is
  the `.hero .sub` paragraph right below it.
- **Demo video** lives in the `#demo` section. Currently a placeholder; replace
  the `.video-frame` `<div>` with a YouTube/Loom `<iframe>` when ready, and
  keep the `aspect-ratio: 16 / 9` CSS rule so the layout doesn't shift.
- **Screenshots** are the three `.shot` tiles. Currently CSS-gradient
  placeholders; swap them for `<img src="assets/screenshot-*.png">` once real
  screenshots land in `assets/`.
- **Footer** copyright + trademark line is locked — keep it in sync with the
  repo `README.md` footer.

## Deploying

Any static host works:

```bash
# Local preview
python -m http.server -d landing 8080

# Or with any of: Cloudflare Pages, GitHub Pages, Netlify, Vercel,
# or a plain S3 bucket + CloudFront.
```

If hosting on a subdomain like `bodhiorchard.com`, set the document root to the
`landing/` directory so paths like `assets/bodhiorchard-logo.png` resolve as
`/assets/bodhiorchard-logo.png`.
