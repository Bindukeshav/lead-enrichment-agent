"""Headless-browser crawling layer.

Fetches a company homepage, discovers relevant subpages (about/team/contact/
pricing/company), and returns rendered HTML for each so JS-heavy sites are
handled correctly.
"""
from __future__ import annotations

import logging
from importlib import import_module
from urllib.parse import urljoin, urlparse

_playwright_api = import_module("playwright.sync_api")
sync_playwright = _playwright_api.sync_playwright
PWTimeoutError = _playwright_api.TimeoutError

logger = logging.getLogger(__name__)

RELEVANT_PATH_KEYWORDS = (
    "about",
    "team",
    "company",
    "contact",
    "pricing",
    "leadership",
    "who-we-are",
)

MAX_SUBPAGES = 3
NAV_TIMEOUT_MS = 45_000


def _normalize_domain(domain: str) -> str:
    domain = domain.strip()
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    return domain


def _is_relevant_link(href: str, base_netloc: str) -> bool:
    try:
        parsed = urlparse(href)
    except ValueError:
        return False
    # Only follow same-domain links
    if parsed.netloc and parsed.netloc != base_netloc:
        return False
    path = parsed.path.lower()
    return any(keyword in path for keyword in RELEVANT_PATH_KEYWORDS)


class SiteScraper:
    """Fetches a homepage + a handful of relevant subpages for one domain."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def fetch_site(self, domain: str) -> dict[str, str]:
        """Returns {url: rendered_html} for the homepage and discovered subpages.

        Never raises on a single page failure — logs and skips it instead, so
        one bad domain can't crash a multi-domain run.
        """
        base_url = _normalize_domain(domain)
        base_netloc = urlparse(base_url).netloc
        pages: dict[str, str] = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (compatible; LeadEnrichmentBot/1.0; "
                    "+https://example.com/bot)"
                )
            )
            page = context.new_page()
            page.set_default_navigation_timeout(NAV_TIMEOUT_MS)

            homepage_html, links = self._safe_load(page, base_url)
            if homepage_html is None:
                context.close()
                browser.close()
                raise RuntimeError(f"Could not load homepage for {domain}")
            pages[base_url] = homepage_html

            subpage_links = [l for l in links if _is_relevant_link(l, base_netloc)]
            # de-dupe while preserving order, cap to MAX_SUBPAGES
            seen = set()
            deduped = []
            for link in subpage_links:
                full = urljoin(base_url, link)
                if full not in seen:
                    seen.add(full)
                    deduped.append(full)

            for link in deduped[:MAX_SUBPAGES]:
                html, _ = self._safe_load(page, link)
                if html:
                    pages[link] = html

            context.close()
            browser.close()

        return pages

    def _safe_load(self, page, url: str) -> tuple[str | None, list[str]]:
        """Load a page, return (html, discovered_hrefs). Returns (None, []) on failure."""
        try:
            response = page.goto(url, wait_until="networkidle")
            if response is not None and response.status >= 400:
                logger.warning("Non-OK status %s for %s", response.status, url)
                return None, []
            html = page.content()
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))"
            )
            hrefs = [h for h in hrefs if h]
            return html, hrefs
        except PWTimeoutError:
            logger.warning("Timeout loading %s", url)
            return None, []
        except Exception as exc:  # noqa: BLE001 - deliberately broad, never crash the run
            logger.warning("Failed to load %s: %s", url, exc)
            return None, []
