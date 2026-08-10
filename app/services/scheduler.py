"""Stage 13 -- config-driven collection scheduler.

No in-process daemon: this module is a *resolver*, meant to be invoked by
an external OS-level scheduler (Windows Task Scheduler / cron) 3x/day per
platform. It answers "which sources are due right now" and hands them to
that platform's existing run_cycle.execute_cycle().

Cadence is stored in Source.configuration["schedule"] (existing JSON
column, no migration needed):
    {"cadence": "daily", "dayparts": ["morning"]}
    {"cadence": "twice_daily", "dayparts": ["morning", "evening"]}

IMPORTANT -- fail-open default: a source with no "schedule" key at all
(true today for every existing Instagram source) is always considered
due. This is deliberate. This stage does not backfill cadence data for
existing sources (that's a data-population follow-up, not code), and a
fail-closed default would silently drop those sources to zero collection
the moment this feature ships -- a worse regression than over-collecting.
"""
import argparse
from typing import List

from sqlalchemy.orm import Session

from app.models.schema import Source
from app.storage.database import SessionLocal

DAYPARTS = ("morning", "midday", "evening")
CADENCES = {"daily": 1, "twice_daily": 2}


def set_schedule(db: Session, source_id: int, cadence: str, dayparts: List[str]) -> Source:
    if cadence not in CADENCES:
        raise ValueError(f"invalid cadence: {cadence!r}, must be one of {sorted(CADENCES)}")
    if len(dayparts) != CADENCES[cadence] or any(d not in DAYPARTS for d in dayparts):
        raise ValueError(f"cadence {cadence!r} requires exactly {CADENCES[cadence]} valid dayparts from {DAYPARTS}, got {dayparts!r}")

    source = db.query(Source).get(source_id)
    if source is None:
        raise ValueError(f"source {source_id} not found")

    config = dict(source.configuration or {})
    config["schedule"] = {"cadence": cadence, "dayparts": dayparts}
    source.configuration = config
    db.commit()
    return source


def get_sources_due(db: Session, platform: str, daypart: str) -> List[Source]:
    if daypart not in DAYPARTS:
        raise ValueError(f"invalid daypart: {daypart!r}, must be one of {DAYPARTS}")

    sources = db.query(Source).filter(Source.platform == platform, Source.enabled == True).all()
    due = []
    for s in sources:
        schedule = (s.configuration or {}).get("schedule")
        if schedule is None:
            due.append(s)  # fail-open: see module docstring
        elif daypart in schedule.get("dayparts", []):
            due.append(s)
    return due


def main():
    ap = argparse.ArgumentParser(description="Cortex Trends scheduled-collection resolver")
    ap.add_argument("action", choices=["run"])
    ap.add_argument("--platform", required=True, choices=["instagram", "youtube", "rss"])
    ap.add_argument("--daypart", required=True, choices=list(DAYPARTS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        due = get_sources_due(db, args.platform, args.daypart)
        print(f"{len(due)} {args.platform} sources due for {args.daypart}")

        if args.platform == "instagram":
            from app.collectors.instagram.run_cycle import execute_cycle
        elif args.platform == "youtube":
            from app.collectors.youtube.run_cycle import execute_cycle
        else:
            from app.collectors.rss.run_cycle import execute_cycle

        execute_cycle(vertical_scope="ALL", sources=due, dry_run=args.dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    main()
