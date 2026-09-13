"""Autonomous Lead Enrichment Agent — CLI entry point.

Usage:
    python main.py --domains postman.com supabase.com vapi.ai --format json
    python main.py --domains postman.com --format csv --out output/result.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys

from dotenv import load_dotenv

from src.agent import run_pipeline

DEFAULT_DOMAINS = ["postman.com", "supabase.com", "vapi.ai"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous lead enrichment agent")
    parser.add_argument(
        "--domains",
        nargs="+",
        default=DEFAULT_DOMAINS,
        help="List of company domains to process",
    )
    parser.add_argument(
        "--format", choices=["json", "csv"], default="json", help="Output file format"
    )
    parser.add_argument(
        "--out", default=None, help="Output file path (defaults to output/output.<format>)"
    )
    parser.add_argument(
        "--linkedin-fallback",
        action="store_true",
        help="Use Tavily search to fill in missing founder LinkedIn URLs ( may incur additional costs )",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached results and re-scrape + re-call the LLM for every domain",
    )
    
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def write_json(results, path: str) -> None:
    with open(path, "w") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)


def write_csv(results, path: str) -> None:
    if not results:
        with open(path, "w") as f:
            f.write("")
        return
    fieldnames = [
        "domain",
        "company_overview",
        "target_audience",
        "contact_points",
        "key_team_members",
        "data_confidence_score",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = r.model_dump()
            row["contact_points"] = "; ".join(row["contact_points"])
            row["key_team_members"] = "; ".join(
                f"{m['name']} ({m.get('role') or 'n/a'}) {m.get('linkedin_url') or ''}".strip()
                for m in row["key_team_members"]
            )
            writer.writerow(row)


def main() -> int:
    load_dotenv()
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    out_path = args.out or f"output/output.{args.format}"

    results, errors, cost_summary = run_pipeline(
        args.domains, use_linkedin_fallback=args.linkedin_fallback, use_cache=not args.no_cache
    )

    if args.format == "json":
        write_json(results, out_path)
    else:
        write_csv(results, out_path)

    print(f"\nProcessed {len(results)} domain(s) successfully, {len(errors)} failed.")
    for err in errors:
        print(f"  FAILED [{err.stage}] {err.domain}: {err.error}")
    print(
        f"Token usage — input: {cost_summary['total_input_tokens']}, "
        f"output: {cost_summary['total_output_tokens']}"
    )
    print(f"Output written to {out_path}")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
