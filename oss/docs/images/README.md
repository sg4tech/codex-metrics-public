# Images

Binary assets used by documentation — primarily README preview images
that appear in link unfurls (Twitter, Slack, Reddit, GitHub repo cards).

## report-preview.png — how to (re)generate

Screenshot of a rendered HTML report. Shown at the top of the main README.

Regenerate with `shot-scraper` (headless Chromium wrapper):

```bash
# One-time setup (pipx + system libs for headless Chrome):
pipx install shot-scraper
shot-scraper install
# On Ubuntu 24.04, if Chromium complains about missing .so files, install:
#   sudo apt-get install -y libatk1.0-0t64 libatk-bridge2.0-0t64 \
#     libatspi2.0-0t64 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
#     libgbm1 libasound2t64 libcups2t64 libnss3 libnspr4

# Then, from the repo root:
ai-agents-metrics render-html --output /tmp/report.html
shot-scraper /tmp/report.html \
  --output oss/docs/images/report-preview.png \
  --width 1200 --height 1600 --wait 1500
```

Dimensions: 1200 × 1600 captures the full report (summary strip + 5 charts).
For a 1200 × 630 OG-card variant (link-unfurl preview on Twitter/Slack), add
`--selector "#sh-ledger"` with a tighter height to grab just the fold.
