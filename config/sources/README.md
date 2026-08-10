# Source config registry (Stage 12)

Each file is a JSON array of source records for one platform, consumed by
`scripts/seed_sources.py`. Record shape:

```json
{
  "external_id": "channel_or_handle",
  "url": "https://...",
  "name": "Display name",
  "vertical": "GENERAL",
  "priority": 1,
  "enabled": true
}
```

`vertical` must be explicit. There is no auto-classification of MEDICAL —
an unset `vertical` defaults to GENERAL, never MEDICAL.

For `rss` sources specifically, `url` is the feed's XML endpoint (the RSS/
Atom URL itself), not the site's homepage. Per-article attribution/site
links come from each entry's own link, not the source-level `url`.

## Status (2026-08-10)

| Platform  | File          | Real sources registered |
|-----------|---------------|--------------------------|
| instagram | `../pages.json` (legacy path, still read directly by the Instagram collector) | 19 |
| youtube   | `youtube.json`  | 0 — **NOT_READY** |
| rss       | `rss.json`      | 6 (all GENERAL) — verified live via `requests`+`feedparser` on 2026-08-10, see below |

`youtube.json` is intentionally empty — no fabricated channels have been
added. `rss.json` has 6 real, individually-verified Tamil news feeds
(bbc_tamil, puthiyathalaimurai, polimernews, vikatan, oneindia_tamil,
dailythanthi) as a starter set proving the RSS collector end-to-end; this
is well short of the 100-source production target by design (Stage 13
scope explicitly does not attempt full source curation — see the stage
plan). Both files should keep growing with real, verified sources over
time.
