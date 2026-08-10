"""Full pipeline orchestrator: collection -> embeddings -> clustering ->
trend scoring -> optional LLM enrichment, as one command instead of five
separately-remembered manual steps.

Each downstream stage genuinely depends on the previous one succeeding
(clustering needs embeddings, scoring needs clusters), so those failures
are hard-blocking. Collection is different: per spec, one platform's
collection trouble must never prevent scoring whatever content already
exists from the others, so collection failures are logged and the
pipeline continues regardless.

Each stage is invoked as a subprocess of its own existing, already-working
CLI script (app.collectors, app.processing.build_embeddings,
app.clustering.run_clustering, app.processing.trend_intelligence,
app.processing.llm_enrichment) rather than importing and calling their
argparse-based main() functions directly -- those scripts were built and
tested as standalone CLI entrypoints, not as importable library functions,
and reusing them via subprocess avoids risky changes to already-working
Stage 8/9 code.
"""
import argparse
import subprocess
import sys
from typing import List, Optional


def _run_module(module_name: str, args: Optional[List[str]] = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", module_name] + (args or [])
    return subprocess.run(cmd, capture_output=True, text=True)


def _step_report(result: subprocess.CompletedProcess) -> dict:
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-1000:] if result.stdout else "",
        "stderr_tail": result.stderr[-1000:] if result.stderr else "",
    }


def run_full_pipeline(
    platforms: Optional[List[str]] = None,
    daypart: Optional[str] = None,
    enrich: bool = False,
    embedding_limit: int = 200,
    dry_run: bool = False,
) -> dict:
    platforms = platforms or ["instagram", "youtube", "rss"]
    report = {"platforms": {}, "embeddings": None, "clustering": None, "trend_scoring": None, "enrichment": None}

    for platform in platforms:
        if daypart:
            args = ["run", "--platform", platform, "--daypart", daypart]
            if dry_run:
                args.append("--dry-run")
            result = _run_module("app.services.scheduler", args)
        else:
            args = ["--platform", platform]
            if dry_run:
                args.append("--dry-run")
            result = _run_module("app.collectors", args)
        report["platforms"][platform] = _step_report(result)

    embeddings_result = _run_module("app.processing.build_embeddings", ["--limit", str(embedding_limit)])
    report["embeddings"] = _step_report(embeddings_result)
    if not report["embeddings"]["ok"]:
        report["error"] = "embeddings step failed -- aborting clustering/trend scoring, which both depend on it"
        return report

    clustering_result = _run_module("app.clustering.run_clustering")
    report["clustering"] = _step_report(clustering_result)
    if not report["clustering"]["ok"]:
        report["error"] = "clustering step failed -- aborting trend scoring, which depends on it"
        return report

    trend_result = _run_module("app.processing.trend_intelligence")
    report["trend_scoring"] = _step_report(trend_result)

    if enrich and report["trend_scoring"]["ok"]:
        enrichment_result = _run_module("app.processing.llm_enrichment", ["enrich"])
        report["enrichment"] = _step_report(enrichment_result)

    return report


def main():
    parser = argparse.ArgumentParser(description="Run the full Cortex Trends pipeline end-to-end")
    parser.add_argument("--platforms", default="instagram,youtube,rss", help="Comma-separated platform list")
    parser.add_argument("--daypart", default=None, choices=["morning", "afternoon", "evening"],
                         help="If set, resolves due sources via the scheduler instead of collecting everything")
    parser.add_argument("--enrich", action="store_true", help="Also run LLM enrichment after trend scoring")
    parser.add_argument("--embedding-limit", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    report = run_full_pipeline(
        platforms=platforms, daypart=args.daypart, enrich=args.enrich,
        embedding_limit=args.embedding_limit, dry_run=args.dry_run,
    )

    print("=" * 60)
    print("CORTEX TRENDS -- FULL PIPELINE RUN")
    print("=" * 60)
    for platform, result in report["platforms"].items():
        print(f"Collection [{platform}]: {'OK' if result['ok'] else 'FAILED'}")
    if report["embeddings"]:
        print(f"Embeddings: {'OK' if report['embeddings']['ok'] else 'FAILED'}")
    if report["clustering"]:
        print(f"Clustering: {'OK' if report['clustering']['ok'] else 'FAILED'}")
    if report["trend_scoring"]:
        print(f"Trend scoring: {'OK' if report['trend_scoring']['ok'] else 'FAILED'}")
    if report["enrichment"]:
        print(f"LLM enrichment: {'OK' if report['enrichment']['ok'] else 'FAILED'}")
    if report.get("error"):
        print(f"\nStopped early: {report['error']}")
    print("=" * 60)

    if report.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
