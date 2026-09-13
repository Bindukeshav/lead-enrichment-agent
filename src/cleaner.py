"""Turns raw rendered HTML into clean markdown-ish text for the LLM.

Goal: never feed a full HTML tree to the model. Strip scripts/styles/svg/nav
boilerplate first so token usage (and latency/cost) stays low.
"""
from bs4 import BeautifulSoup

STRIP_TAGS = ("script", "style", "svg", "nav", "footer", "noscript", "iframe", "form")
MAX_CHARS_PER_PAGE = 3000  # keep each page's contribution bounded


def _html_to_markdown(html: str) -> str:
    """Convert the small set of HTML structures we retain to markdown."""
    soup = BeautifulSoup(html, "html.parser")

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(heading.name[1])
        heading.replace_with(f"{'#' * level} {heading.get_text(' ', strip=True)}")

    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True)
        link.replace_with(f"[{text}]({link['href']})" if text else link["href"])

    for item in soup.find_all("li"):
        item.insert_before("- ")

    return soup.get_text("\n")


def html_to_clean_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Drop elements that are almost certainly boilerplate/menus
    for tag in soup.find_all(attrs={"class": lambda c: c and "cookie" in " ".join(c).lower()}):
        tag.decompose()

    main = soup.find("main") or soup.body or soup
    markdown_text = _html_to_markdown(str(main))

    # Collapse excess blank lines
    lines = [line.strip() for line in markdown_text.splitlines()]
    lines = [line for line in lines if line]
    cleaned = "\n".join(lines)

    return cleaned[:MAX_CHARS_PER_PAGE]


def build_context(pages: dict[str, str]) -> str:
    """Combine cleaned markdown from multiple pages into one LLM-ready context block."""
    sections = []
    for url, html in pages.items():
        cleaned = html_to_clean_markdown(html)
        if cleaned:
            sections.append(f"### Source: {url}\n{cleaned}")
    return "\n\n".join(sections)
