"""Manual/interactive entrypoint for app.processing.normalize_raw_content.
create_caption_sources() -- the real logic now lives there and runs
automatically at the end of every collection cycle (Stage 14). This script
remains useful for an ad hoc rebuild against existing data.
"""
import argparse
from sqlalchemy.orm import Session
from app.storage.database import SessionLocal
from app.processing.normalize_raw_content import create_caption_sources


def rebuild():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        report = create_caption_sources(db, limit=args.limit)
    finally:
        db.close()

    print("========================================")
    print("CONTENTSOURCE REBUILD RESULTS")
    print("========================================")
    print(f"Caption ContentSources before: {report['captions_before']}")
    print(f"Caption ContentSources after: {report['captions_after']}")
    print(f"New Caption ContentSources: {report['new_sources']}")
    print(f"Duplicates prevented: {report['duplicates']}")
    print(f"Skipped (empty text): {report['skipped_empty']}")


if __name__ == "__main__":
    rebuild()
