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

## Status (2026-08-10)

| Platform  | File          | Real sources registered |
|-----------|---------------|--------------------------|
| instagram | `../pages.json` (legacy path, still read directly by the Instagram collector) | 19 |
| youtube   | `youtube.json`  | 0 — **NOT_READY** |
| news(rss) | `rss.json`      | 0 — **NOT_READY** |

`youtube.json` and `rss.json` are intentionally empty. No fabricated
channels or feeds have been added. Populate them with real, verified
YouTube Shorts channels / Tamil RSS feed URLs to move those platforms out
of NOT_READY.
