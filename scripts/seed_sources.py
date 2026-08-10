"""Stage 12 — production source seeding entrypoint.

Reads real source config for each platform and idempotently upserts them
into the `sources` table via app.services.source_registry. Also sweeps
existing rows for validation failures and quarantines them (no deletes).

Usage (run from project root, DATABASE_URL / .env pointing at the target DB):
    python scripts/seed_sources.py
"""
import json
import os

from app.storage.database import SessionLocal
from app.services.source_registry import (
    seed_platform,
    quarantine_invalid_sources,
    governance_snapshot,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLATFORM_CONFIG_PATHS = {
    "instagram": os.path.join(BASE_DIR, "config", "pages.json"),
    "youtube": os.path.join(BASE_DIR, "config", "sources", "youtube.json"),
    "news": os.path.join(BASE_DIR, "config", "sources", "rss.json"),
}


def load_records(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run():
    db = SessionLocal()
    try:
        seed_reports = {}
        for platform, path in PLATFORM_CONFIG_PATHS.items():
            records = load_records(path)
            report = seed_platform(db, platform, records)
            seed_reports[platform] = report

        quarantined = quarantine_invalid_sources(db)
        snapshot = governance_snapshot(db)

        print("=" * 60)
        print("STAGE 12 SOURCE SEEDING")
        print("=" * 60)
        for platform, report in seed_reports.items():
            print(f"\nPlatform: {platform}")
            print(f"  added:     {len(report.added)} {report.added}")
            print(f"  updated:   {len(report.updated)} {report.updated}")
            print(f"  unchanged: {len(report.unchanged)}")
            print(f"  rejected:  {len(report.rejected)}")
            for r in report.rejected:
                print(f"    - {r['record'].get('external_id') or r['record'].get('username')}: {r['errors']}")

        print(f"\nQuarantined existing invalid sources: {len(quarantined)}")
        for q in quarantined:
            print(f"  - id={q['id']} external_id={q['external_id']} reasons={q['errors']}")

        print("\nGovernance snapshot:")
        print(json.dumps(snapshot, indent=2))

        return {
            "seed_reports": {
                platform: {
                    "added": r.added,
                    "updated": r.updated,
                    "unchanged": r.unchanged,
                    "rejected": r.rejected,
                }
                for platform, r in seed_reports.items()
            },
            "quarantined": quarantined,
            "snapshot": snapshot,
        }
    finally:
        db.close()


if __name__ == "__main__":
    run()
