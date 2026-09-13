"""Top-level orchestration: for each domain, scrape -> clean -> extract,
never letting one domain's failure kill the whole run.

Domains are processed concurrently (bounded thread pool) since each one is
an independent, mostly I/O-bound unit of work (network + LLM call) — this
keeps a multi-domain run from being needlessly slow while still isolating
failures per domain.

Results are cached to disk per domain (cache/<domain>.json) so re-running
the same domain doesn't re-scrape or re-call the LLM — useful both to save
API cost/rate-limit budget and to avoid redundant work on reruns.
"""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .cleaner import build_context
from .extractor import LLMExtractor
from .models import LeadEnrichmentResult, ScrapeError
from .scraper import SiteScraper
from .search_fallback import enrich_missing_linkedin_urls

logger = logging.getLogger(__name__)

MAX_WORKERS = 3  # bounded so we don't hammer sites or rate limits
CACHE_DIR = Path("cache")


def _cache_path(domain: str) -> Path:
    safe_name = domain.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe_name}.json"


def _load_from_cache(domain: str) -> LeadEnrichmentResult | None:
    path = _cache_path(domain)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return LeadEnrichmentResult(**data)
    except Exception as exc:  # noqa: BLE001 - a corrupt cache file should never crash a run
        logger.warning("Ignoring unreadable cache file for %s: %s", domain, exc)
        return None


def _save_to_cache(domain: str, result: LeadEnrichmentResult) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(domain).write_text(json.dumps(result.model_dump(), indent=2))


def _process_domain(
    domain: str,
    extractor: LLMExtractor,
    use_linkedin_fallback: bool,
    use_cache: bool,
) -> tuple[LeadEnrichmentResult | None, ScrapeError | None, dict]:
    if use_cache:
        cached = _load_from_cache(domain)
        if cached is not None:
            logger.info("Using cached result for %s (skipped scrape + LLM call)", domain)
            return cached, None, {"input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}

    # Each thread gets its own SiteScraper/Playwright instance — Playwright
    # sync API is not thread-safe to share across threads.
    scraper = SiteScraper(headless=True)

    try:
        pages = scraper.fetch_site(domain)
    except Exception as exc:  # noqa: BLE001
        logger.error("Fetch failed for %s: %s", domain, exc)
        return None, ScrapeError(domain=domain, error=str(exc), stage="fetch"), {}

    context = build_context(pages)
    if not context.strip():
        return (
            None,
            ScrapeError(domain=domain, error="No usable content extracted", stage="fetch"),
            {},
        )

    try:
        result, usage = extractor.extract(domain, context)
    except Exception as exc:  # noqa: BLE001
        logger.error("Extraction failed for %s: %s", domain, exc)
        return None, ScrapeError(domain=domain, error=str(exc), stage="extract"), {}

    if use_linkedin_fallback:
        enrich_missing_linkedin_urls(result, domain)

    logger.info(
        "Done %s (tokens in=%s out=%s, est. cost=$%.6f)",
        domain,
        usage["input_tokens"],
        usage["output_tokens"],
        usage["estimated_cost_usd"],
    )

    if use_cache:
        _save_to_cache(domain, result)

    return result, None, usage


def run_pipeline(
    domains: list[str],
    use_linkedin_fallback: bool = False,
    max_workers: int = MAX_WORKERS,
    use_cache: bool = True,
) -> tuple[list[LeadEnrichmentResult], list[ScrapeError], dict]:
    extractor = LLMExtractor()
    token_lock = threading.Lock()  # LLMExtractor's counters are mutated across threads

    results: list[LeadEnrichmentResult] = []
    errors: list[ScrapeError] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _process_domain, domain, extractor, use_linkedin_fallback, use_cache
            ): domain
            for domain in domains
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                result, error, _usage = future.result()
            except Exception as exc:  # noqa: BLE001 - guard against unexpected thread errors
                logger.error("Unexpected failure processing %s: %s", domain, exc)
                errors.append(ScrapeError(domain=domain, error=str(exc), stage="fetch"))
                continue

            if result is not None:
                with token_lock:
                    results.append(result)
            if error is not None:
                with token_lock:
                    errors.append(error)

    cost_summary = {
        "total_input_tokens": extractor.total_input_tokens,
        "total_output_tokens": extractor.total_output_tokens,
    }
    return results, errors, cost_summary