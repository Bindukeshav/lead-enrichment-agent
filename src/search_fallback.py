"""Optional bonus: use Tavily search to fill in missing LinkedIn URLs for
team members that were found by name but had no LinkedIn URL on-page.

This is best-effort — if TAVILY_API_KEY isn't set, or a lookup fails, we
just skip it and leave the field empty rather than raising.
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def find_linkedin_url(person_name: str, company_domain: str) -> str | None:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return None

    try:
        from tavily import TavilyClient  # optional dependency

        client = TavilyClient(api_key=api_key)
        query = f'"{person_name}" {company_domain} LinkedIn'
        results = client.search(query=query, max_results=3)
        for item in results.get("results", []):
            url = item.get("url", "")
            if "linkedin.com/in/" in url:
                return url
    except Exception as exc:  # noqa: BLE001
        logger.warning("LinkedIn fallback search failed for %s: %s", person_name, exc)

    return None


def enrich_missing_linkedin_urls(result, company_domain: str) -> None:
    """Mutates result.key_team_members in place, filling missing linkedin_url fields."""
    for member in result.key_team_members:
        if not member.linkedin_url:
            member.linkedin_url = find_linkedin_url(member.name, company_domain)
