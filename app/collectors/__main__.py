"""Stage 13 -- unified multi-platform collector CLI.

Usage:
    python -m app.collectors --platform {instagram,youtube,rss} [--vertical-scope ALL] [--dry-run]

This is additive: Instagram's existing app/collectors/instagram/__main__.py
(a richer single-page test-mode CLI) stays in place unchanged.
"""
import argparse


def main():
    parser = argparse.ArgumentParser(description="Cortex Trends multi-platform collector CLI")
    parser.add_argument("--platform", required=True, choices=["instagram", "youtube", "rss"])
    parser.add_argument("--vertical-scope", default="ALL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.platform == "instagram":
        from app.collectors.instagram.run_cycle import execute_cycle
    elif args.platform == "youtube":
        from app.collectors.youtube.run_cycle import execute_cycle
    else:
        from app.collectors.rss.run_cycle import execute_cycle

    execute_cycle(vertical_scope=args.vertical_scope, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
